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
    AdaptiveMealCalculation,
    CarbAbsorptionProfile,
    DoseStrategySettings,
    Meal,
    MealCalculation,
    MealCarbGroup,
    MealComponentAbsorption,
    MealDoseEvent,
    Patient,
    TherapyLimit,
    TimeOfDayProfile,
    UserSettings,
    ClinicalModelSetting,
)

from app.schema.schemas import (
    AdaptiveMealCalculationResponse,
    MealCalculationCreate,
    MealCalculationResponse,
    AdaptiveMealModelsResponse,
)

from app.services.therapy_context import (
    TherapyContextError,
    resolve_therapy_context,
)

from app.services.meal_absorption import (
    MealAbsorptionSummary,
    resolve_meal_absorption_summary,
)

from app.services.fat_protein_model import (
    FAT_PROTEIN_MODEL_VERSION,
    FatProteinModelResult,
    calculate_fat_protein_model,
)

from app.services.adaptive_dose import (
    AdaptiveMealRequirement,
    calculate_primary_adaptive_meal_requirement_from_state,
    calculate_warsaw_adaptive_meal_requirement_from_state,
)

ADAPTIVE_MEAL_CALCULATION_VERSION = "adaptive_meal_requirement_v1"
PRIMARY_ADAPTIVE_MODEL_VERSION = "primary_v1"
WARSAW_ADAPTIVE_MODEL_VERSION = "warsaw_v1"

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

_COMPONENT_DERIVED_ABSORPTION_SOURCES = frozenset({
    "meal_category_rule_v1",
    "component_single_v1",
    "component_uniform_v1",
    "component_mixed_v1",
})


def _meal_absorption_classification_is_component_replaceable(
    meal: Meal,
) -> bool:
    """Return True when component snapshots may establish/refresh the summary."""
    if _meal_absorption_classification_is_unset(meal):
        return True

    return (
        meal.absorption_classification_source
        in _COMPONENT_DERIVED_ABSORPTION_SOURCES
    )

def _persist_component_absorption_classification(
    *,
    meal: Meal,
    summary: MealAbsorptionSummary,
) -> bool:
    """Persist a component-derived meal absorption summary.

    Explicit/manual meal classifications remain immutable.
    Mixed meals intentionally have no single absorption profile id.
    """
    if not _meal_absorption_classification_is_component_replaceable(meal):
        return False

    meal.absorption_profile_id = summary.profile_id
    meal.absorption_profile_key = summary.profile_key
    meal.absorption_classification_source = (
        summary.classification_source
    )
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

def _calculate_fat_protein_snapshot(
    *,
    meal: Meal,
    strategy: DoseStrategySettings,
) -> FatProteinModelResult:
    """Resolve the B2.3 delayed-nutrient snapshot for one calculation."""
    return calculate_fat_protein_model(
        fat_grams=(
            meal.fat_grams
            if meal.fat_grams is not None
            else Decimal("0")
        ),
        protein_grams=(
            meal.protein_grams
            if meal.protein_grams is not None
            else Decimal("0")
        ),
        mode=strategy.fat_protein_mode,
        scaling_percent=strategy.fat_protein_scaling_percent,
    )

def _build_adaptive_meal_calculation(
    *,
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    insulin_to_carb_ratio: Decimal,
    result: AdaptiveMealRequirement,
    adaptive_model_version: str,
) -> AdaptiveMealCalculation:
    """
    Build one immutable B2.4a persistence snapshot from a domain result.

    This helper performs no therapy-context resolution and no physiological
    recommendation logic. The ICR supplied here must come from the immutable
    originating MealCalculation snapshot.
    """
    return AdaptiveMealCalculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        consumed_carbs_grams=result.consumed_carbs_grams,
        fat_protein_effective_carb_equivalent_grams=(
            result.fat_protein_effective_carb_equivalent_grams
        ),
        insulin_to_carb_ratio=Decimal(str(insulin_to_carb_ratio)),
        actual_administered_units=result.actual_administered_units,
        carb_insulin_requirement_units=(
            result.carb_insulin_requirement_units
        ),
        fat_protein_insulin_requirement_units=(
            result.fat_protein_insulin_requirement_units
        ),
        total_meal_requirement_units=(
            result.total_meal_requirement_units
        ),
        remaining_meal_requirement_units=(
            result.remaining_meal_requirement_units
        ),
        adaptive_calculation_version=(
            ADAPTIVE_MEAL_CALCULATION_VERSION
        ),
        adaptive_model_version=adaptive_model_version,
    )

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

    component_absorptions_result = await db.execute(
        select(MealComponentAbsorption)
        .join(
            MealCarbGroup,
            MealCarbGroup.id
            == MealComponentAbsorption.meal_carb_group_id,
        )
        .where(
            MealCarbGroup.meal_id == meal.id,
            MealComponentAbsorption.patient_id == patient_id,
        )
    )

    component_absorptions = (
        component_absorptions_result.scalars().all()
    )

    try:
        absorption_summary = resolve_meal_absorption_summary(
            component_absorptions
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    _persist_component_absorption_classification(
        meal=meal,
        summary=absorption_summary,
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

    fat_protein_snapshot = _calculate_fat_protein_snapshot(
        meal=meal,
        strategy=strategy,
    )

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
        fat_protein_model_mode=fat_protein_snapshot.mode,
        fat_protein_model_scaling_percent=(
            fat_protein_snapshot.scaling_percent
        ),
        fat_protein_fat_grams=fat_protein_snapshot.fat_grams,
        fat_protein_protein_grams=fat_protein_snapshot.protein_grams,
        fat_protein_fat_kcal=fat_protein_snapshot.fat_kcal,
        fat_protein_protein_kcal=fat_protein_snapshot.protein_kcal,
        fat_protein_total_kcal=(
            fat_protein_snapshot.total_fat_protein_kcal
        ),
        fat_protein_units=fat_protein_snapshot.fat_protein_units,
        fat_protein_theoretical_carb_equivalent_grams=(
            fat_protein_snapshot.theoretical_carb_equivalent_grams
        ),
        fat_protein_scaled_carb_equivalent_grams=(
            fat_protein_snapshot.scaled_carb_equivalent_grams
        ),
        fat_protein_effective_carb_equivalent_grams=(
            fat_protein_snapshot.effective_carb_equivalent_grams
        ),
        fat_protein_model_version=FAT_PROTEIN_MODEL_VERSION,
        absorption_profile_id=absorption_summary.profile_id,
        absorption_profile_key=absorption_summary.profile_key,
        absorption_duration_minutes=absorption_summary.duration_minutes,
        absorption_delay_minutes=absorption_summary.delay_minutes,
        absorption_classification_source=(
            absorption_summary.classification_source
        ),
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
            f"absorption={absorption_summary.profile_key}; "
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

@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/adaptive",
    response_model=AdaptiveMealCalculationResponse,
    status_code=201,
)
async def calculate_adaptive_meal(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Create one immutable B2.4a meal-accounting snapshot.

    Authoritative inputs come only from persisted server state:

      - the originating MealCalculation therapy/B2.3 snapshot
      - current actual component consumption
      - actual executed MealDoseEvent state

    Planned carbohydrate and planned insulin are never treated as actual.

    remaining_meal_requirement_units is meal accounting only. It is not yet
    a safe immediate insulin recommendation.
    """

    calculation_result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id
        )
    )
    original_calculation = calculation_result.scalar_one_or_none()

    if (
        original_calculation is None
        or original_calculation.patient_id != patient_id
        or original_calculation.meal_id != meal_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Meal calculation not found",
        )

    if original_calculation.carb_factor_g_per_unit is None:
        raise HTTPException(
            status_code=409,
            detail="Originating calculation lacks adaptive dosing snapshots",
        )

    component_result = await db.execute(
        select(MealCarbGroup)
        .where(
            MealCarbGroup.meal_id == meal_id,
        )
        .order_by(MealCarbGroup.group_number)
    )
    components = component_result.scalars().all()

    dose_event_result = await db.execute(
        select(MealDoseEvent)
        .where(
            MealDoseEvent.calculation_id == calculation_id,
        )
        .order_by(MealDoseEvent.dose_number)
    )
    dose_events = dose_event_result.scalars().all()

    # Establish an explicit ORM -> domain boundary.
    #
    # The B2.4a service intentionally consumes only actual state. Planned
    # carbohydrate and planned insulin fields are not supplied.
    component_state = [
        {
            "consumed_carbs_grams": component.consumed_carbs_grams,
        }
        for component in components
    ]

    dose_event_state = [
        {
            "status": dose_event.status,
            "actual_units": dose_event.actual_units,
        }
        for dose_event in dose_events
    ]

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=components,
        insulin_to_carb_ratio=original_calculation.carb_factor_g_per_unit,
        dose_events=dose_events,
        primary_fat_protein_addon_percent=(
            original_calculation.fat_protein_addon_percent
        ),
    )

    adaptive_calculation = _build_adaptive_meal_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        insulin_to_carb_ratio=(
            original_calculation.carb_factor_g_per_unit
        ),
        result=result,
        adaptive_model_version=PRIMARY_ADAPTIVE_MODEL_VERSION,
    )

    try:
        db.add(adaptive_calculation)
        await db.commit()
        await db.refresh(adaptive_calculation)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to persist adaptive meal calculation",
        ) from exc

    return adaptive_calculation



@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/adaptive/warsaw",
    response_model=AdaptiveMealCalculationResponse,
    status_code=201,
)
async def calculate_warsaw_adaptive_meal(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Create one immutable Warsaw v1 adaptive meal-accounting snapshot.

    Warsaw is an independent alternative model. It consumes the immutable
    Warsaw fat/protein snapshot from the originating MealCalculation and
    never consumes the Primary fat/protein add-on parameter.

    Planned carbohydrate and planned insulin are never treated as actual.

    remaining_meal_requirement_units is meal accounting only. It is not yet
    a safe immediate insulin recommendation.
    """

    calculation_result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id
        )
    )
    original_calculation = calculation_result.scalar_one_or_none()

    if (
        original_calculation is None
        or original_calculation.patient_id != patient_id
        or original_calculation.meal_id != meal_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Meal calculation not found",
        )

    if (
        original_calculation.carb_factor_g_per_unit is None
        or original_calculation.fat_protein_effective_carb_equivalent_grams
        is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Originating calculation lacks Warsaw adaptive snapshots",
        )

    component_result = await db.execute(
        select(MealCarbGroup)
        .where(
            MealCarbGroup.meal_id == meal_id,
        )
        .order_by(MealCarbGroup.group_number)
    )
    components = component_result.scalars().all()

    dose_event_result = await db.execute(
        select(MealDoseEvent)
        .where(
            MealDoseEvent.calculation_id == calculation_id,
        )
        .order_by(MealDoseEvent.dose_number)
    )
    dose_events = dose_event_result.scalars().all()

    result = calculate_warsaw_adaptive_meal_requirement_from_state(
        components=components,
        fat_protein_effective_carb_equivalent_grams=(
            original_calculation
            .fat_protein_effective_carb_equivalent_grams
        ),
        insulin_to_carb_ratio=(
            original_calculation.carb_factor_g_per_unit
        ),
        dose_events=dose_events,
    )

    adaptive_calculation = _build_adaptive_meal_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        insulin_to_carb_ratio=(
            original_calculation.carb_factor_g_per_unit
        ),
        result=result,
        adaptive_model_version=WARSAW_ADAPTIVE_MODEL_VERSION,
    )

    try:
        db.add(adaptive_calculation)
        await db.commit()
        await db.refresh(adaptive_calculation)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to persist Warsaw adaptive meal calculation",
        ) from exc

    return adaptive_calculation

@router.post(
    "/patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/adaptive/models",
    response_model=AdaptiveMealModelsResponse,
    status_code=201,
)
async def calculate_adaptive_models(
    patient_id: UUID,
    meal_id: UUID,
    calculation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Create parallel immutable adaptive model snapshots.

    The Primary model always executes.

    Alternative models execute only when enabled by global back-office
    clinical-model configuration.

    All branches consume the same authoritative persisted meal state and
    actual insulin state. Model mathematics remain independent and results
    are persisted together in one transaction.
    """
    calculation_result = await db.execute(
        select(MealCalculation).where(
            MealCalculation.id == calculation_id
        )
    )
    original_calculation = calculation_result.scalar_one_or_none()

    if (
        original_calculation is None
        or original_calculation.patient_id != patient_id
        or original_calculation.meal_id != meal_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Meal calculation not found",
        )

    # Primary requires its historical ICR snapshot and its own immutable
    # fat/protein add-on parameter. It never consumes Warsaw state.
    if (
        original_calculation.carb_factor_g_per_unit is None
        or original_calculation.fat_protein_addon_percent is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Originating calculation lacks adaptive dosing snapshots",
        )

    component_result = await db.execute(
        select(MealCarbGroup)
        .where(
            MealCarbGroup.meal_id == meal_id,
        )
        .order_by(MealCarbGroup.group_number)
    )
    components = component_result.scalars().all()

    dose_event_result = await db.execute(
        select(MealDoseEvent)
        .where(
            MealDoseEvent.calculation_id == calculation_id,
        )
        .order_by(MealDoseEvent.dose_number)
    )
    dose_events = dose_event_result.scalars().all()

    model_setting_result = await db.execute(
        select(ClinicalModelSetting)
        .where(
            ClinicalModelSetting.enabled.is_(True),
        )
        .order_by(
            ClinicalModelSetting.role,
            ClinicalModelSetting.model_key,
            ClinicalModelSetting.model_version,
        )
    )
    enabled_models = model_setting_result.scalars().all()

    # ---------------------------------------------------------------
    # Primary branch
    # ---------------------------------------------------------------
    #
    # Primary always executes. Its calculation is independent of every
    # alternative model and consumes only Primary-specific snapshots.
    primary_result = calculate_primary_adaptive_meal_requirement_from_state(
        components=components,
        insulin_to_carb_ratio=(
            original_calculation.carb_factor_g_per_unit
        ),
        dose_events=dose_events,
        primary_fat_protein_addon_percent=(
            original_calculation.fat_protein_addon_percent
        ),
    )

    primary_snapshot = _build_adaptive_meal_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        insulin_to_carb_ratio=(
            original_calculation.carb_factor_g_per_unit
        ),
        result=primary_result,
        adaptive_model_version=PRIMARY_ADAPTIVE_MODEL_VERSION,
    )

    snapshots = [primary_snapshot]
    alternatives = []

    # ---------------------------------------------------------------
    # Alternative branches
    # ---------------------------------------------------------------
    #
    # Model exposure comes exclusively from back-office configuration.
    # Each enabled alternative remains mathematically independent.
    warsaw_enabled = any(
        model.model_key == "warsaw"
        and model.model_version == WARSAW_ADAPTIVE_MODEL_VERSION
        and model.role == "alternative"
        for model in enabled_models
    )

    if warsaw_enabled:
        if (
            original_calculation
            .fat_protein_effective_carb_equivalent_grams
            is None
        ):
            raise HTTPException(
                status_code=409,
                detail="Originating calculation lacks Warsaw adaptive snapshots",
            )

        warsaw_result = (
            calculate_warsaw_adaptive_meal_requirement_from_state(
                components=components,
                fat_protein_effective_carb_equivalent_grams=(
                    original_calculation
                    .fat_protein_effective_carb_equivalent_grams
                ),
                insulin_to_carb_ratio=(
                    original_calculation.carb_factor_g_per_unit
                ),
                dose_events=dose_events,
            )
        )

        warsaw_snapshot = _build_adaptive_meal_calculation(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            insulin_to_carb_ratio=(
                original_calculation.carb_factor_g_per_unit
            ),
            result=warsaw_result,
            adaptive_model_version=WARSAW_ADAPTIVE_MODEL_VERSION,
        )

        snapshots.append(warsaw_snapshot)
        alternatives.append(warsaw_snapshot)

    # ---------------------------------------------------------------
    # Atomic persistence boundary
    # ---------------------------------------------------------------
    #
    # Either every model snapshot generated by this orchestration is
    # persisted, or none is.
    try:
        for snapshot in snapshots:
            db.add(snapshot)

        await db.commit()

        for snapshot in snapshots:
            await db.refresh(snapshot)

    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to persist adaptive model calculations",
        ) from exc

    return AdaptiveMealModelsResponse(
        primary=primary_snapshot,
        alternatives=alternatives,
    )