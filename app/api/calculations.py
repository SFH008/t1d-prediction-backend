"""
Meal calculation endpoints.

Calculation is deliberately separate from Dose 1 / Dose 2.
It creates an immutable snapshot of the meal inputs and therapy rules used
to produce the calculated recommendation.
"""

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Meal, MealCalculation, Patient
from app.schema.schemas import (
    MealCalculationCreate,
    MealCalculationResponse,
)


router = APIRouter(tags=["Meal Calculations"])


def _round_units(value: Decimal) -> Decimal:
    """Round calculated insulin to 0.01 units."""
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculate",
    response_model=MealCalculationResponse,
    status_code=201,
)
async def calculate_meal(
    patient_id: UUID,
    meal_id: UUID,
    calculation_create: MealCalculationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Calculate a meal dose without creating a dose event."""

    patient_result = await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found",
        )

    meal_result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.patient_id == patient_id,
        )
    )
    meal = meal_result.scalar_one_or_none()

    if meal is None:
        raise HTTPException(
            status_code=404,
            detail=f"Meal {meal_id} not found",
        )

    carb_total = Decimal(str(meal.total_carbs_grams))
    carb_factor = Decimal(
        str(calculation_create.carb_factor_g_per_unit)
    )

    carbohydrate_dose = _round_units(
        carb_total / carb_factor
    )

    correction_dose = Decimal("0")
    if (
        calculation_create.glucose_mg_dl is not None
        and calculation_create.target_glucose_mg_dl is not None
        and calculation_create.insulin_sensitivity_mg_dl_per_unit
        is not None
    ):
        correction_dose = _round_units(
            (
                Decimal(str(calculation_create.glucose_mg_dl))
                - Decimal(str(calculation_create.target_glucose_mg_dl))
            )
            / Decimal(
                str(
                    calculation_create
                    .insulin_sensitivity_mg_dl_per_unit
                )
            )
        )

        # A correction should not become negative insulin.
        correction_dose = max(correction_dose, Decimal("0"))

    calculated_dose = _round_units(
        carbohydrate_dose + correction_dose
    )

    calculation = MealCalculation(
        meal_id=meal.id,
        patient_id=patient_id,
        glucose_mg_dl=calculation_create.glucose_mg_dl,
        target_glucose_mg_dl=calculation_create.target_glucose_mg_dl,
        carb_factor_g_per_unit=carb_factor,
        insulin_sensitivity_mg_dl_per_unit=(
            calculation_create.insulin_sensitivity_mg_dl_per_unit
        ),
        carbohydrate_total_grams=carb_total,
        carbohydrate_dose_units=carbohydrate_dose,
        correction_dose_units=correction_dose,
        calculated_dose_units=calculated_dose,
        calculation_version="1",
    )

    db.add(calculation)
    await db.commit()
    await db.refresh(calculation)

    return calculation
