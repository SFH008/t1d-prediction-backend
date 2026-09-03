from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Patient,
    PatientAbsorptionForecast,
    PatientAbsorptionHistory,
)
from app.schema.schemas import (
    PatientAbsorptionTimelineResponse,
)


router = APIRouter(
    tags=["Absorption"],
)


@router.get(
    "/patients/{patient_id}/absorption-timeline",
    response_model=PatientAbsorptionTimelineResponse,
)
async def get_absorption_timeline(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the persisted six-hour historical and six-hour forecast
    absorption timeline for one patient.

    This endpoint is read-only and does not trigger recalculation.
    """

    patient_result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id
        )
    )

    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found",
        )

    # Load newest historical points first so LIMIT 72 returns the latest
    # six-hour window, then reverse for ascending frontend display.
    history_result = await db.execute(
        select(PatientAbsorptionHistory)
        .where(
            PatientAbsorptionHistory.patient_id
            == patient_id,
            PatientAbsorptionHistory.derivation_mode
            == "original",
        )
        .order_by(
            PatientAbsorptionHistory.interval_start.desc()
        )
        .limit(72)
    )

    history = list(
        reversed(
            history_result.scalars().all()
        )
    )

    # Current forecast rows are operational state and already represent
    # the active 72-point forecast for the patient.
    forecast_result = await db.execute(
        select(PatientAbsorptionForecast)
        .where(
            PatientAbsorptionForecast.patient_id
            == patient_id
        )
        .order_by(
            PatientAbsorptionForecast.interval_start
        )
    )

    forecast = forecast_result.scalars().all()

    return PatientAbsorptionTimelineResponse(
        patient_id=patient_id,
        history=history,
        forecast=forecast,
    )