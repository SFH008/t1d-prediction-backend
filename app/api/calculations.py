"""
Meal calculation endpoints.

Calculation version 2 remains available through its pure helper for regression
coverage. Version 3 builds a patient-specific split-dose plan and stores an
immutable snapshot of every therapy, absorption, and strategy input used.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    CarbAbsorptionProfile,
    DoseStrategySettings,
    Meal,
    MealCalculation,
    MealDoseEvent,
    Patient,
    TherapyLimit,
    TimeOfDayProfile,
    UserSettings,
)
from app.schema.schemas import (
    MealCalculationCreate,
    MealCalculationResponse,
)
from app.services.therapy_context import (
    TherapyContextError,
    resolve_therapy_context,
)


router = APIRouter(tags=["Meal Calculations"])


def _round_units(value: Decimal) -> Decimal:
    """Legacy version-2 rounding to 0.01 units."""
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _round_down_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    """Conservatively round insulin downward to a positive device increment."""
    value = Decimal(str(value))
    increment = Decimal(str(increment))

    if increment <= 0:
        raise ValueError("Insulin rounding increment must be positive")

    if value <= 0:
        return Decimal("0")

    steps = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * increment


class MealDoseCalculationResult:
    """Pure in-memory result of the legacy version-2 meal calculation."""

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
    """Pure legacy version-2 calculation retained for regression coverage."""
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


@dataclass(frozen=True)
class SplitDoseCalculationResult:
    """Pure calculation-version-3 split-dose result."""

    base_carbohydrate_grams: Decimal
    fat_protein_addon_percent: Decimal
    fat_protein_addon_grams: Decimal
    effective_carbohydrate_grams: Decimal
    dose_1_share_percent: Decimal
    dose_2_share_percent: Decimal
    dose_1_carbohydrate_grams: Decimal
    dose_2_carbohydrate_grams: Decimal
    dose_1_carbohydrate_units: Decimal
    dose_2_carbohydrate_units: Decimal
    correction_dose_units: Decimal
    dose_1_units: Decimal
    dose_2_units: Decimal
    total_planned_dose_units: Decimal
    carbohydrate_dose_units: Decimal


def calculate_split_dose(
    *,
    carbohydrate_total_grams,
    fat_protein_addon_percent,
    dose_1_share_percent,
    meal_icr_g_per_unit,
    dose_2_icr_g_per_unit,
    insulin_rounding_increment_units,
    glucose_mg_dl=None,
    target_glucose_mg_dl=None,
    meal_isf_mg_dl_per_unit=None,
) -> SplitDoseCalculationResult:
    """
    Calculate version-3 Dose 1 and Dose 2.

    Dose 1 receives its carbohydrate share at the meal-time ICR plus the full
    positive correction. Dose 2 receives the remaining carbohydrate share at
    the ICR active when Dose 2 is scheduled. Final administered doses are
    rounded downward to the configured insulin increment.
    """
    base_carbs = Decimal(str(carbohydrate_total_grams))
    addon_percent = Decimal(str(fat_protein_addon_percent or 0))
    dose_1_share = Decimal(str(dose_1_share_percent))
    meal_icr = Decimal(str(meal_icr_g_per_unit))
    dose_2_icr = Decimal(str(dose_2_icr_g_per_unit))
    increment = Decimal(str(insulin_rounding_increment_units))

    if base_carbs < 0:
        raise ValueError("Carbohydrate total cannot be negative")
    if addon_percent < 0:
        raise ValueError("Fat/protein add-on cannot be negative")
    if not Decimal("0") <= dose_1_share <= Decimal("100"):
        raise ValueError("Dose 1 share must be between 0 and 100")
    if meal_icr <= 0 or dose_2_icr <= 0:
        raise ValueError("ICR must be positive")

    dose_2_share = Decimal("100") - dose_1_share
    addon_grams = base_carbs * addon_percent / Decimal("100")
    effective_carbs = base_carbs + addon_grams

    dose_1_carbs = effective_carbs * dose_1_share / Decimal("100")
    dose_2_carbs = effective_carbs - dose_1_carbs

    dose_1_carb_units = dose_1_carbs / meal_icr
    dose_2_carb_units = dose_2_carbs / dose_2_icr

    correction = Decimal("0")
    if (
        glucose_mg_dl is not None
        and target_glucose_mg_dl is not None
        and meal_isf_mg_dl_per_unit is not None
    ):
        isf = Decimal(str(meal_isf_mg_dl_per_unit))
        if isf <= 0:
            raise ValueError("ISF must be positive")
        correction = max(
            Decimal("0"),
            (
                Decimal(str(glucose_mg_dl))
                - Decimal(str(target_glucose_mg_dl))
            ) / isf,
        )

    dose_1 = _round_down_to_increment(
        dose_1_carb_units + correction,
        increment,
    )
    dose_2 = _round_down_to_increment(
        dose_2_carb_units,
        increment,
    )
    total = dose_1 + dose_2

    return SplitDoseCalculationResult(
        base_carbohydrate_grams=base_carbs,
        fat_protein_addon_percent=addon_percent,
        fat_protein_addon_grams=addon_grams,
        effective_carbohydrate_grams=effective_carbs,
        dose_1_share_percent=dose_1_share,
        dose_2_share_percent=dose_2_share,
        dose_1_carbohydrate_grams=dose_1_carbs,
        dose_2_carbohydrate_grams=dose_2_carbs,
        dose_1_carbohydrate_units=dose_1_carb_units,
        dose_2_carbohydrate_units=dose_2_carb_units,
        correction_dose_units=correction,
        dose_1_units=dose_1,
        dose_2_units=dose_2,
        total_planned_dose_units=total,
        carbohydrate_dose_units=dose_1_carb_units + dose_2_carb_units,
    )


def _meal_absorption_classification_is_unset(meal: Meal) -> bool:
    """Return True only when no explicit/stored meal classification exists."""
    return (
        meal.absorption_profile_id is None
        and meal.absorption_profile_key is None
        and meal.absorption_classification_source is None
    )


def _persist_derived_absorption_classification(
    *,
    meal: Meal,
    absorption_profile: CarbAbsorptionProfile,
    classification_source: str,
) -> bool:
    """Persist derived classification without overwriting explicit meal metadata."""
    if not _meal_absorption_classification_is_unset(meal):
        return False

    meal.absorption_profile_id = absorption_profile.id
    meal.absorption_profile_key = absorption_profile.profile_key
    meal.absorption_classification_source = classification_source
    return True


def _absorption_profile_key_for_meal(meal: Meal) -> tuple[str, str]:
    """Baseline deterministic meal-type classifier; future models can replace it."""
    if meal.absorption_profile_key:
        return meal.absorption_profile_key, (
            meal.absorption_classification_source or "stored"
        )

    category = (meal.meal_category or "").strip().lower().replace("-", "_").replace(" ", "_")

    very_fast = {
        "hypo", "hypo_treatment", "glucose", "glucose_tabs", "glucose_tablets",
        "glucose_gel", "juice_glucose_mix",
    }
    fast = {
        "juice", "liquid_fruit", "sugary_drink", "sugary_drinks", "liquid_carbs",
    }
    slow = {
        "pizza", "pasta", "high_fat", "high_protein", "high_fat_high_protein",
    }

    if category in very_fast:
        return "very_fast", "meal_category_rule_v1"
    if category in fast:
        return "fast", "meal_category_rule_v1"
    if category in slow:
        return "slow", "meal_category_rule_v1"
    return "medium", "meal_category_rule_v1"


def _planned_dose_events_for_calculation(
    *,
    calculation: MealCalculation,
    meal: Meal,
) -> list[MealDoseEvent]:
    """Build the immutable execution plan corresponding to one v3 calculation."""
    if calculation.id is None:
        raise ValueError("Calculation must have an id before dose events are built")
    if calculation.dose_2_timestamp is None:
        raise ValueError("Version-3 calculation requires a Dose 2 timestamp")
    if calculation.dose_1_units is None or calculation.dose_2_units is None:
        raise ValueError("Version-3 calculation requires both planned doses")

    return [
        MealDoseEvent(
            patient_id=calculation.patient_id,
            meal_id=calculation.meal_id,
            calculation_id=calculation.id,
            dose_number=1,
            planned_timestamp=meal.meal_timestamp,
            planned_units=calculation.dose_1_units,
            status="planned",
        ),
        MealDoseEvent(
            patient_id=calculation.patient_id,
            meal_id=calculation.meal_id,
            calculation_id=calculation.id,
            dose_number=2,
            planned_timestamp=calculation.dose_2_timestamp,
            planned_units=calculation.dose_2_units,
            status="planned",
        ),
    ]


async def _persist_calculation_with_dose_plan(
    *,
    db: AsyncSession,
    calculation: MealCalculation,
    meal: Meal,
) -> None:
    """Persist calculation and its two planned tracker events atomically."""
    try:
        db.add(calculation)
        # UUID defaults are populated during flush; tracker rows need the exact id.
        await db.flush()
        db.add_all(
            _planned_dose_events_for_calculation(
                calculation=calculation,
                meal=meal,
            )
        )
        await db.commit()
    except (SQLAlchemyError, ValueError):
        await db.rollback()
        raise

    await db.refresh(calculation)


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
    """Create and persist a version-3 split-dose recommendation."""

    patient_result = await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    meal_result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.patient_id == patient_id,
        )
    )
    meal = meal_result.scalar_one_or_none()
    if meal is None:
        raise HTTPException(status_code=404, detail=f"Meal {meal_id} not found")

    profiles_result = await db.execute(
        select(TimeOfDayProfile).where(
            TimeOfDayProfile.patient_id == patient_id,
        )
    )
    time_of_day_profiles = profiles_result.scalars().all()

    limits_result = await db.execute(
        select(TherapyLimit).where(
            TherapyLimit.patient_id == patient_id,
        )
    )
    therapy_limits = limits_result.scalars().all()

    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.patient_id == patient_id)
    )
    settings = settings_result.scalar_one_or_none()

    strategy_result = await db.execute(
        select(DoseStrategySettings).where(
            DoseStrategySettings.patient_id == patient_id,
            DoseStrategySettings.is_active.is_(True),
        )
    )
    strategy = strategy_result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(
            status_code=422,
            detail="No active dose strategy settings are configured for this patient",
        )

    try:
        meal_context = resolve_therapy_context(
            meal_timestamp=meal.meal_timestamp,
            time_of_day_profiles=time_of_day_profiles,
            therapy_limits=therapy_limits,
            settings=settings,
        )

        dose_2_timestamp = meal.meal_timestamp + timedelta(
            minutes=strategy.dose_2_delay_minutes
        )
        dose_2_context = resolve_therapy_context(
            meal_timestamp=dose_2_timestamp,
            time_of_day_profiles=time_of_day_profiles,
            therapy_limits=therapy_limits,
            settings=settings,
        )
    except TherapyContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    absorption_key, classification_source = _absorption_profile_key_for_meal(meal)
    absorption_result = await db.execute(
        select(CarbAbsorptionProfile).where(
            CarbAbsorptionProfile.patient_id == patient_id,
            CarbAbsorptionProfile.profile_key == absorption_key,
            CarbAbsorptionProfile.is_active.is_(True),
        )
    )
    absorption_profile = absorption_result.scalar_one_or_none()
    if absorption_profile is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No active carbohydrate absorption profile is configured "
                f"for meal class '{absorption_key}'"
            ),
        )

    _persist_derived_absorption_classification(
        meal=meal,
        absorption_profile=absorption_profile,
        classification_source=classification_source,
    )

    addon_percent = (
        meal.fat_protein_addon_percent
        if meal.fat_protein_addon_percent is not None
        else strategy.fat_protein_addon_percent
    )

    try:
        result = calculate_split_dose(
            carbohydrate_total_grams=meal.total_carbs_grams,
            fat_protein_addon_percent=addon_percent,
            dose_1_share_percent=strategy.dose_1_share_percent,
            meal_icr_g_per_unit=meal_context.carb_factor_g_per_unit,
            dose_2_icr_g_per_unit=dose_2_context.carb_factor_g_per_unit,
            insulin_rounding_increment_units=strategy.insulin_rounding_increment_units,
            glucose_mg_dl=calculation_create.glucose_mg_dl,
            target_glucose_mg_dl=meal_context.target_glucose_mg_dl,
            meal_isf_mg_dl_per_unit=meal_context.insulin_sensitivity_mg_dl_per_unit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    calculation = MealCalculation(
        meal_id=meal.id,
        patient_id=patient_id,
        glucose_mg_dl=calculation_create.glucose_mg_dl,
        target_glucose_mg_dl=meal_context.target_glucose_mg_dl,
        carb_factor_g_per_unit=meal_context.carb_factor_g_per_unit,
        insulin_sensitivity_mg_dl_per_unit=meal_context.insulin_sensitivity_mg_dl_per_unit,
        carbohydrate_total_grams=result.base_carbohydrate_grams,
        carbohydrate_dose_units=result.carbohydrate_dose_units,
        correction_dose_units=result.correction_dose_units,
        calculated_dose_units=result.total_planned_dose_units,
        meal_therapy_profile_id=meal_context.profile_id,
        meal_basal_drift_mg_dl_per_hour=meal_context.basal_drift_mg_dl_per_hour,
        base_carbohydrate_grams=result.base_carbohydrate_grams,
        fat_protein_addon_percent=result.fat_protein_addon_percent,
        fat_protein_addon_grams=result.fat_protein_addon_grams,
        effective_carbohydrate_grams=result.effective_carbohydrate_grams,
        absorption_profile_id=absorption_profile.id,
        absorption_profile_key=absorption_profile.profile_key,
        absorption_duration_minutes=absorption_profile.duration_minutes,
        absorption_delay_minutes=absorption_profile.absorption_delay_minutes,
        absorption_classification_source=classification_source,
        dose_1_share_percent=result.dose_1_share_percent,
        dose_2_share_percent=result.dose_2_share_percent,
        dose_2_delay_minutes=strategy.dose_2_delay_minutes,
        dose_2_timestamp=dose_2_timestamp,
        insulin_rounding_increment_units=strategy.insulin_rounding_increment_units,
        strategy_source=strategy.strategy_source,
        strategy_version=strategy.strategy_version,
        dose_2_therapy_profile_id=dose_2_context.profile_id,
        dose_2_carb_factor_g_per_unit=dose_2_context.carb_factor_g_per_unit,
        dose_2_insulin_sensitivity_mg_dl_per_unit=(
            dose_2_context.insulin_sensitivity_mg_dl_per_unit
        ),
        dose_2_target_glucose_mg_dl=dose_2_context.target_glucose_mg_dl,
        dose_2_basal_drift_mg_dl_per_hour=dose_2_context.basal_drift_mg_dl_per_hour,
        dose_1_carbohydrate_grams=result.dose_1_carbohydrate_grams,
        dose_2_carbohydrate_grams=result.dose_2_carbohydrate_grams,
        dose_1_carbohydrate_units=result.dose_1_carbohydrate_units,
        dose_1_units=result.dose_1_units,
        dose_2_carbohydrate_units=result.dose_2_carbohydrate_units,
        dose_2_units=result.dose_2_units,
        total_planned_dose_units=result.total_planned_dose_units,
        manual_insulin_given_units=calculation_create.manual_insulin_given_units,
        calculation_version="3",
        notes=(
            f"Meal therapy context: {meal_context.source}; "
            f"Dose 2 therapy context: {dose_2_context.source}; "
            f"absorption={absorption_profile.profile_key}; "
            f"strategy={strategy.strategy_source}"
        ),
    )

    try:
        await _persist_calculation_with_dose_plan(
            db=db,
            calculation=calculation,
            meal=meal,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist calculation and dose plan",
        ) from exc

    return calculation
