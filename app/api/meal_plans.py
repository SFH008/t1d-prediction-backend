"""Frontend-facing consolidated Meal Plan read endpoints.

These endpoints do not calculate or mutate therapy. They compose the immutable
MealCalculation snapshot with its meal metadata and Multi-Dose Tracker events so
React can render a complete current or historical plan from one response.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Meal, MealCalculation, MealDoseEvent
from app.schema.schemas import (
    MealPlanAbsorptionResponse,
    MealPlanCalculationResponse,
    MealPlanMealResponse,
    MealPlanResponse,
)

router = APIRouter(tags=["Meal Plans"])


def _build_meal_plan_response(
    *,
    meal: Meal,
    calculation: MealCalculation,
    dose_events: list[MealDoseEvent],
) -> MealPlanResponse:
    """Compose one frontend-safe read model from immutable persisted state."""
    return MealPlanResponse(
        meal=MealPlanMealResponse(
            id=meal.id,
            patient_id=meal.patient_id,
            meal_timestamp=meal.meal_timestamp,
            meal_category=meal.meal_category,
            total_carbs_grams=float(meal.total_carbs_grams),
            absorption_profile_key=meal.absorption_profile_key,
            absorption_classification_source=meal.absorption_classification_source,
        ),
        calculation=MealPlanCalculationResponse(
            id=calculation.id,
            calculation_version=calculation.calculation_version,
            calculated_at=calculation.calculated_at,
            glucose_mg_dl=(
                float(calculation.glucose_mg_dl)
                if calculation.glucose_mg_dl is not None
                else None
            ),
            target_glucose_mg_dl=(
                float(calculation.target_glucose_mg_dl)
                if calculation.target_glucose_mg_dl is not None
                else None
            ),
            meal_icr_g_per_unit=(
                float(calculation.carb_factor_g_per_unit)
                if calculation.carb_factor_g_per_unit is not None
                else None
            ),
            meal_isf_mg_dl_per_unit=(
                float(calculation.insulin_sensitivity_mg_dl_per_unit)
                if calculation.insulin_sensitivity_mg_dl_per_unit is not None
                else None
            ),
            meal_basal_drift_mg_dl_per_hour=(
                float(calculation.meal_basal_drift_mg_dl_per_hour)
                if calculation.meal_basal_drift_mg_dl_per_hour is not None
                else None
            ),
            dose_2_icr_g_per_unit=(
                float(calculation.dose_2_carb_factor_g_per_unit)
                if calculation.dose_2_carb_factor_g_per_unit is not None
                else None
            ),
            dose_2_isf_mg_dl_per_unit=(
                float(calculation.dose_2_insulin_sensitivity_mg_dl_per_unit)
                if calculation.dose_2_insulin_sensitivity_mg_dl_per_unit is not None
                else None
            ),
            dose_2_basal_drift_mg_dl_per_hour=(
                float(calculation.dose_2_basal_drift_mg_dl_per_hour)
                if calculation.dose_2_basal_drift_mg_dl_per_hour is not None
                else None
            ),
            dose_1_share_percent=(
                float(calculation.dose_1_share_percent)
                if calculation.dose_1_share_percent is not None
                else None
            ),
            dose_2_share_percent=(
                float(calculation.dose_2_share_percent)
                if calculation.dose_2_share_percent is not None
                else None
            ),
            dose_2_delay_minutes=calculation.dose_2_delay_minutes,
            dose_2_timestamp=calculation.dose_2_timestamp,
            dose_1_units=(
                float(calculation.dose_1_units)
                if calculation.dose_1_units is not None
                else None
            ),
            dose_2_units=(
                float(calculation.dose_2_units)
                if calculation.dose_2_units is not None
                else None
            ),
            total_planned_dose_units=(
                float(calculation.total_planned_dose_units)
                if calculation.total_planned_dose_units is not None
                else None
            ),
            strategy_source=calculation.strategy_source,
            strategy_version=calculation.strategy_version,
        ),
        absorption=MealPlanAbsorptionResponse(
            profile_key=calculation.absorption_profile_key,
            duration_minutes=calculation.absorption_duration_minutes,
            delay_minutes=calculation.absorption_delay_minutes,
            classification_source=calculation.absorption_classification_source,
        ),
        dose_events=sorted(dose_events, key=lambda item: item.dose_number),
    )


async def _load_meal(
    *, patient_id: UUID, meal_id: UUID, db: AsyncSession
) -> Meal:
    result = await db.execute(
        select(Meal).where(Meal.id == meal_id, Meal.patient_id == patient_id)
    )
    meal = result.scalar_one_or_none()
    if meal is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    return meal


async def _load_dose_events(
    *, patient_id: UUID, meal_id: UUID, calculation_id: UUID, db: AsyncSession
) -> list[MealDoseEvent]:
    result = await db.execute(
        select(MealDoseEvent)
        .where(
            MealDoseEvent.patient_id == patient_id,
            MealDoseEvent.meal_id == meal_id,
            MealDoseEvent.calculation_id == calculation_id,
        )
        .order_by(MealDoseEvent.dose_number)
    )
    return list(result.scalars().all())


@router.get(
    "/patients/{patient_id}/meals/{meal_id}/plan",
    response_model=MealPlanResponse,
)
async def get_latest_meal_plan(
    patient_id: UUID,
    meal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return the latest Version 3 plan for a meal."""
    meal = await _load_meal(patient_id=patient_id, meal_id=meal_id, db=db)

    result = await db.execute(
        select(MealCalculation)
        .where(
            MealCalculation.patient_id == patient_id,
            MealCalculation.meal_id == meal_id,
            MealCalculation.calculation_version == "3",
        )
        .order_by(MealCalculation.calculated_at.desc(), MealCalculation.id.desc())
        .limit(1)
    )
    calculation = result.scalar_one_or_none()
    if calculation is None:
        raise HTTPException(status_code=404, detail="No Version 3 meal plan found")

    dose_events = await _load_dose_events(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation.id,
        db=db,
    )
    return _build_meal_plan_response(
        meal=meal,
        calculation=calculation,
        dose_events=dose_events,
    )


@router.get(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/plan",
    response_model=MealPlanResponse,
)
async def get_historical_meal_plan(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return one immutable historical Version 3 plan."""
    meal = await _load_meal(patient_id=patient_id, meal_id=meal_id, db=db)

    result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id,
            MealCalculation.patient_id == patient_id,
            MealCalculation.meal_id == meal_id,
            MealCalculation.calculation_version == "3",
        )
    )
    calculation = result.scalar_one_or_none()
    if calculation is None:
        raise HTTPException(status_code=404, detail="Version 3 meal calculation not found")

    dose_events = await _load_dose_events(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation.id,
        db=db,
    )
    return _build_meal_plan_response(
        meal=meal,
        calculation=calculation,
        dose_events=dose_events,
    )
