"""Multi-Dose Tracker execution endpoints.

Planned doses belong to an immutable MealCalculation. Actual administration is
recorded separately and, when insulin is given, linked to the canonical
InsulinEvent ledger in the same transaction.
"""

from datetime import timezone
from decimal import Decimal
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import InsulinEvent, Meal, MealCalculation, MealDoseEvent
from app.schema.schemas import (
    MealDoseEventAdjust,
    MealDoseEventConfirm,
    MealDoseEventResponse,
    MealDoseEventSkip,
)
from app.services.meal_lifecycle import (
    complete_meal_recording_if_ready,
)

router = APIRouter(tags=["Meal Dose Tracker"])

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"given", "adjusted", "skipped", "cancelled"}


def _decimal_units(value) -> Decimal:
    return Decimal(str(value))


def _utc_naive(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _ensure_planned(event: MealDoseEvent) -> None:
    if event.status in _TERMINAL_STATUSES or event.insulin_event_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Dose {event.dose_number} has already been finalized as {event.status}",
        )
    if event.status != "planned":
        raise HTTPException(
            status_code=409,
            detail=f"Dose {event.dose_number} is not in a confirmable planned state",
        )


async def _load_dose_event(
    *,
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    dose_number: int,
    db: AsyncSession,
) -> MealDoseEvent:
    if dose_number not in (1, 2):
        raise HTTPException(status_code=422, detail="dose_number must be 1 or 2")

    calculation_result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id,
            MealCalculation.patient_id == patient_id,
            MealCalculation.meal_id == meal_id,
        )
    )
    if calculation_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Meal calculation not found")

    meal_result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.patient_id == patient_id,
        )
    )
    meal = meal_result.scalar_one_or_none()

    if meal is None:
        raise HTTPException(status_code=404, detail="Meal not found")

    if meal.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Dose execution can only be recorded for an active meal",
        )

    event_result = await db.execute(
        select(MealDoseEvent).where(
            MealDoseEvent.patient_id == patient_id,
            MealDoseEvent.meal_id == meal_id,
            MealDoseEvent.calculation_id == calculation_id,
            MealDoseEvent.dose_number == dose_number,
        )
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail=f"Dose {dose_number} event not found")
    return event


async def _record_administered_dose(
    *,
    event: MealDoseEvent,
    actual_units: Decimal,
    actual_timestamp,
    delivery_method: str | None,
    notes: str | None,
    status: str,
    adjustment_reason: str | None,
    db: AsyncSession,
) -> MealDoseEvent:
    _ensure_planned(event)

    persisted_actual_timestamp = _utc_naive(actual_timestamp)

    insulin_event = InsulinEvent(
        patient_id=event.patient_id,
        insulin_type="bolus",
        dose_units=actual_units,
        timestamp=persisted_actual_timestamp,
        delivery_method=delivery_method,
        source="meal_dose_tracker",
    )

    try:
        db.add(insulin_event)
        await db.flush()

        event.actual_timestamp = persisted_actual_timestamp
        event.actual_units = actual_units
        event.status = status
        event.adjustment_reason = adjustment_reason
        event.notes = notes
        event.insulin_event_id = insulin_event.id

        # Persist the terminal dose state before evaluating the complete
        # Actual Meal recording state in this same transaction.
        await db.flush()

        await complete_meal_recording_if_ready(
            db=db,
            patient_id=event.patient_id,
            meal_id=event.meal_id,
        )

        await db.commit()
        await db.refresh(event)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception(
            "Failed to persist dose administration: %s",
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to persist dose administration")

    return event


@router.get(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/dose-events",
    response_model=list[MealDoseEventResponse],
)
async def get_meal_dose_events(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    calculation_result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id,
            MealCalculation.patient_id == patient_id,
            MealCalculation.meal_id == meal_id,
        )
    )
    if calculation_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Meal calculation not found")

    result = await db.execute(
        select(MealDoseEvent)
        .where(
            MealDoseEvent.patient_id == patient_id,
            MealDoseEvent.meal_id == meal_id,
            MealDoseEvent.calculation_id == calculation_id,
        )
        .order_by(MealDoseEvent.dose_number)
    )
    return result.scalars().all()


@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/dose-events/{dose_number}/confirm",
    response_model=MealDoseEventResponse,
)
async def confirm_meal_dose_event(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    dose_number: int,
    payload: MealDoseEventConfirm,
    db: AsyncSession = Depends(get_db),
):
    event = await _load_dose_event(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=dose_number,
        db=db,
    )
    actual_units = _decimal_units(payload.actual_units)
    if actual_units != _decimal_units(event.planned_units):
        raise HTTPException(
            status_code=422,
            detail="Confirmed units must equal planned units; use adjust for a changed dose",
        )

    return await _record_administered_dose(
        event=event,
        actual_units=actual_units,
        actual_timestamp=payload.actual_timestamp,
        delivery_method=payload.delivery_method,
        notes=payload.notes,
        status="given",
        adjustment_reason=None,
        db=db,
    )


@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/dose-events/{dose_number}/adjust",
    response_model=MealDoseEventResponse,
)
async def adjust_meal_dose_event(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    dose_number: int,
    payload: MealDoseEventAdjust,
    db: AsyncSession = Depends(get_db),
):
    event = await _load_dose_event(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=dose_number,
        db=db,
    )
    actual_units = _decimal_units(payload.actual_units)
    if actual_units == _decimal_units(event.planned_units):
        raise HTTPException(
            status_code=422,
            detail="Adjusted units must differ from planned units; use confirm when unchanged",
        )

    return await _record_administered_dose(
        event=event,
        actual_units=actual_units,
        actual_timestamp=payload.actual_timestamp,
        delivery_method=payload.delivery_method,
        notes=payload.notes,
        status="adjusted",
        adjustment_reason=payload.adjustment_reason,
        db=db,
    )


@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/dose-events/{dose_number}/skip",
    response_model=MealDoseEventResponse,
)
async def skip_meal_dose_event(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    dose_number: int,
    payload: MealDoseEventSkip,
    db: AsyncSession = Depends(get_db),
):
    event = await _load_dose_event(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=dose_number,
        db=db,
    )
    _ensure_planned(event)

    try:
        event.status = "skipped"
        event.adjustment_reason = payload.adjustment_reason
        event.notes = payload.notes
        event.actual_timestamp = None
        event.actual_units = None
        event.insulin_event_id = None

        # Make the terminal skip visible before evaluating meal completion.
        await db.flush()

        await complete_meal_recording_if_ready(
            db=db,
            patient_id=event.patient_id,
            meal_id=event.meal_id,
        )

        await db.commit()
        await db.refresh(event)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist skipped dose")

    return event
