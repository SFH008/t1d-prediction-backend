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

class MealDoseCalculationResult:
    """Pure in-memory result of a meal dose calculation."""

    def __init__(
        self,
        carbohydrate_dose_units: Decimal,
        correction_dose_units: Decimal,
        calculated_dose_units: Decimal,
    ):
        self.carbohydrate_dose_units = carbohydrate_dose_units
        self.correction_dose_units = correction_dose_units
        self.calculated_dose_units = calculated_dose_units


def calculate_meal_dose(
    carbohydrate_total_grams,
    carb_factor_g_per_unit,
    glucose_mg_dl=None,
    target_glucose_mg_dl=None,
    insulin_sensitivity_mg_dl_per_unit=None,
):
    """
    Pure meal dose calculation.

    This function performs no database access and creates no database
    objects. It is therefore safe to test independently of the API/database.
    """
    carb_total = Decimal(str(carbohydrate_total_grams))
    carb_factor = Decimal(str(carb_factor_g_per_unit))

    carbohydrate_dose = _round_units(
        carb_total / carb_factor
    )

    correction_dose = Decimal("0")

    if (
        glucose_mg_dl is not None
        and target_glucose_mg_dl is not None
        and insulin_sensitivity_mg_dl_per_unit is not None
    ):
        correction_dose = _round_units(
            (
                Decimal(str(glucose_mg_dl))
                - Decimal(str(target_glucose_mg_dl))
            )
            / Decimal(str(insulin_sensitivity_mg_dl_per_unit))
        )

        correction_dose = max(
            correction_dose,
            Decimal("0"),
        )

    calculated_dose = _round_units(
        carbohydrate_dose + correction_dose
    )

    return MealDoseCalculationResult(
        carbohydrate_dose_units=carbohydrate_dose,
        correction_dose_units=correction_dose,
        calculated_dose_units=calculated_dose,
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

    calculation_result = calculate_meal_dose(
        carbohydrate_total_grams=meal.total_carbs_grams,
        carb_factor_g_per_unit=calculation_create.carb_factor_g_per_unit,
        glucose_mg_dl=calculation_create.glucose_mg_dl,
        target_glucose_mg_dl=calculation_create.target_glucose_mg_dl,
        insulin_sensitivity_mg_dl_per_unit=(
            calculation_create.insulin_sensitivity_mg_dl_per_unit
        ),
    )

    carb_total = Decimal(str(meal.total_carbs_grams))
    carb_factor = Decimal(
        str(calculation_create.carb_factor_g_per_unit)
    )

    carbohydrate_dose = calculation_result.carbohydrate_dose_units
    correction_dose = calculation_result.correction_dose_units
    calculated_dose = calculation_result.calculated_dose_units

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
