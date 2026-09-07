from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class RemainingInsulinRequirement:
    required_units: Decimal
    actual_administered_units: Decimal
    remaining_units: Decimal


def calculate_remaining_insulin_requirement(
    *,
    required_units,
    actual_administered_units,
) -> RemainingInsulinRequirement:
    """
    Calculate remaining insulin requirement from actual administration.

    Planned insulin is intentionally not part of this function.
    """
    required = Decimal(str(required_units))
    administered = (
        Decimal("0")
        if actual_administered_units is None
        else Decimal(str(actual_administered_units))
    )

    if required < 0:
        raise ValueError("Required insulin units cannot be negative")

    if administered < 0:
        raise ValueError(
            "Actual administered insulin units cannot be negative"
        )

    remaining = max(
        Decimal("0"),
        required - administered,
    )

    return RemainingInsulinRequirement(
        required_units=required,
        actual_administered_units=administered,
        remaining_units=remaining,
    )

def calculate_actual_consumed_carbs(
    *,
    consumed_carbs_grams,
) -> Decimal | None:
    """
    Return the complete actual carbohydrate consumption for a meal.

    Adaptive dosing requires complete consumption information:
    - explicit zero is known zero
    - any unknown component keeps the meal total unknown
    - an empty component list is unknown
    """
    values = list(consumed_carbs_grams)

    if not values:
        return None

    total = Decimal("0")

    for value in values:
        if value is None:
            return None

        carbs = Decimal(str(value))

        if carbs < 0:
            raise ValueError(
                "Consumed carbohydrate grams cannot be negative"
            )

        total += carbs

    return total

def calculate_carb_insulin_requirement(
    *,
    consumed_carbs_grams,
    insulin_to_carb_ratio,
) -> Decimal | None:
    """
    Calculate carbohydrate insulin requirement from actual consumed carbs.

    Unknown consumption remains unknown.
    """
    if consumed_carbs_grams is None:
        return None

    carbs = Decimal(str(consumed_carbs_grams))
    icr = Decimal(str(insulin_to_carb_ratio))

    if carbs < 0:
        raise ValueError(
            "Consumed carbohydrate grams cannot be negative"
        )

    if icr <= 0:
        raise ValueError(
            "Insulin-to-carbohydrate ratio must be greater than zero"
        )

    return carbs / icr

@dataclass(frozen=True)
class AdaptiveCarbRequirement:
    consumed_carbs_grams: Decimal | None
    carb_insulin_requirement_units: Decimal | None
    actual_administered_units: Decimal
    remaining_units: Decimal | None


def calculate_adaptive_carb_requirement(
    *,
    consumed_carbs_grams,
    insulin_to_carb_ratio,
    actual_administered_units,
) -> AdaptiveCarbRequirement:
    """
    Compose actual consumption, ICR and actual insulin execution into
    the remaining carbohydrate insulin requirement for the meal.
    """
    carb_requirement = calculate_carb_insulin_requirement(
        consumed_carbs_grams=consumed_carbs_grams,
        insulin_to_carb_ratio=insulin_to_carb_ratio,
    )

    administered = (
        Decimal("0")
        if actual_administered_units is None
        else Decimal(str(actual_administered_units))
    )

    if administered < 0:
        raise ValueError(
            "Actual administered insulin units cannot be negative"
        )

    if carb_requirement is None:
        return AdaptiveCarbRequirement(
            consumed_carbs_grams=None,
            carb_insulin_requirement_units=None,
            actual_administered_units=administered,
            remaining_units=None,
        )

    remaining = calculate_remaining_insulin_requirement(
        required_units=carb_requirement,
        actual_administered_units=administered,
    )

    return AdaptiveCarbRequirement(
        consumed_carbs_grams=Decimal(str(consumed_carbs_grams)),
        carb_insulin_requirement_units=carb_requirement,
        actual_administered_units=remaining.actual_administered_units,
        remaining_units=remaining.remaining_units,
    )

def calculate_fat_protein_insulin_requirement(
    *,
    effective_carb_equivalent_grams,
    insulin_to_carb_ratio,
) -> Decimal:
    """
    Calculate the insulin requirement for the already-authorized
    fat/protein carbohydrate-equivalent contribution.

    This function does not decide whether fat/protein contribution
    is enabled. B2.3 has already resolved that into the effective
    carbohydrate-equivalent value supplied here.
    """
    equivalent = Decimal(str(effective_carb_equivalent_grams))
    icr = Decimal(str(insulin_to_carb_ratio))

    if equivalent < 0:
        raise ValueError(
            "Effective fat/protein carbohydrate equivalent cannot be negative"
        )

    if icr <= 0:
        raise ValueError(
            "Insulin-to-carbohydrate ratio must be greater than zero"
        )

    return equivalent / icr

@dataclass(frozen=True)
class AdaptiveMealRequirement:
    consumed_carbs_grams: Decimal | None
    carb_insulin_requirement_units: Decimal | None

    # Warsaw-specific outputs. NULL means that Warsaw does not apply
    # to the model that produced this adaptive result.
    fat_protein_effective_carb_equivalent_grams: Decimal | None
    fat_protein_insulin_requirement_units: Decimal | None

    total_meal_requirement_units: Decimal | None

    actual_administered_units: Decimal
    remaining_meal_requirement_units: Decimal | None


def calculate_adaptive_meal_requirement(
    *,
    consumed_carbs_grams,
    fat_protein_effective_carb_equivalent_grams,
    insulin_to_carb_ratio,
    actual_administered_units,
) -> AdaptiveMealRequirement:
    """
    Calculate the remaining insulin requirement for one meal.

    Actual carbohydrate consumption and the authorized fat/protein
    contribution remain separate components.

    Planned insulin is intentionally not part of this calculation.
    """
    carb_requirement = calculate_carb_insulin_requirement(
        consumed_carbs_grams=consumed_carbs_grams,
        insulin_to_carb_ratio=insulin_to_carb_ratio,
    )

    fp_equivalent = Decimal(
        str(fat_protein_effective_carb_equivalent_grams)
    )

    fp_requirement = calculate_fat_protein_insulin_requirement(
        effective_carb_equivalent_grams=fp_equivalent,
        insulin_to_carb_ratio=insulin_to_carb_ratio,
    )

    administered = (
        Decimal("0")
        if actual_administered_units is None
        else Decimal(str(actual_administered_units))
    )

    if administered < 0:
        raise ValueError(
            "Actual administered insulin units cannot be negative"
        )

    if carb_requirement is None:
        return AdaptiveMealRequirement(
            consumed_carbs_grams=None,
            carb_insulin_requirement_units=None,
            fat_protein_effective_carb_equivalent_grams=fp_equivalent,
            fat_protein_insulin_requirement_units=fp_requirement,
            total_meal_requirement_units=None,
            actual_administered_units=administered,
            remaining_meal_requirement_units=None,
        )

    total_requirement = carb_requirement + fp_requirement

    remaining = calculate_remaining_insulin_requirement(
        required_units=total_requirement,
        actual_administered_units=administered,
    )

    return AdaptiveMealRequirement(
        consumed_carbs_grams=Decimal(str(consumed_carbs_grams)),
        carb_insulin_requirement_units=carb_requirement,
        fat_protein_effective_carb_equivalent_grams=fp_equivalent,
        fat_protein_insulin_requirement_units=fp_requirement,
        total_meal_requirement_units=total_requirement,
        actual_administered_units=remaining.actual_administered_units,
        remaining_meal_requirement_units=remaining.remaining_units,
    )

def calculate_actual_administered_insulin(
    *,
    dose_events,
) -> Decimal:
    """
    Sum actual administered insulin from executed dose events.

    Events may be mapping-like test/domain values or attribute-based
    persisted ORM rows.

    Only terminal administered states contribute:
      - given
      - adjusted

    Planned insulin is never treated as administered.
    """
    total = Decimal("0")

    for event in dose_events:
        if isinstance(event, dict):
            status = event.get("status")
            actual_units = event.get("actual_units")
        else:
            status = getattr(event, "status", None)
            actual_units = getattr(event, "actual_units", None)

        if status not in {"given", "adjusted"}:
            continue

        if actual_units is None:
            raise ValueError(
                "Administered dose event must have actual insulin units"
            )

        units = Decimal(str(actual_units))

        if units < 0:
            raise ValueError(
                "Actual administered insulin units cannot be negative"
            )

        total += units

    return total
    
def calculate_actual_consumed_carbs_from_components(
    *,
    components,
) -> Decimal | None:
    """
    Extract persisted actual carbohydrate consumption from meal components.

    Components may be mapping-like test/domain values or attribute-based
    persisted ORM rows.

    Planned carbohydrate values are intentionally ignored.

    Delegates NULL/zero/negative semantics to
    calculate_actual_consumed_carbs().
    """

    def consumed_carbs(component):
        if isinstance(component, dict):
            return component.get("consumed_carbs_grams")

        return getattr(component, "consumed_carbs_grams", None)

    return calculate_actual_consumed_carbs(
        consumed_carbs_grams=[
            consumed_carbs(component)
            for component in components
        ]
    )

def calculate_adaptive_meal_requirement_from_state(
    *,
    components,
    fat_protein_effective_carb_equivalent_grams,
    insulin_to_carb_ratio,
    dose_events,
) -> AdaptiveMealRequirement:
    """
    Calculate the adaptive meal requirement from persisted meal state.

    This adapter performs no new dosing arithmetic. It extracts:
      - actual consumed carbohydrate from persisted meal components
      - actual administered insulin from executed dose events

    and delegates the requirement calculation to the existing
    B2.4a domain primitives.

    Planned carbohydrate and planned insulin are intentionally ignored.
    """
    consumed_carbs = calculate_actual_consumed_carbs_from_components(
        components=components,
    )

    actual_administered = calculate_actual_administered_insulin(
        dose_events=dose_events,
    )

    return calculate_adaptive_meal_requirement(
        consumed_carbs_grams=consumed_carbs,
        fat_protein_effective_carb_equivalent_grams=(
            fat_protein_effective_carb_equivalent_grams
        ),
        insulin_to_carb_ratio=insulin_to_carb_ratio,
        actual_administered_units=actual_administered,
    )

def calculate_primary_adaptive_meal_requirement_from_state(
    *,
    components,
    insulin_to_carb_ratio,
    dose_events,
    primary_fat_protein_addon_percent,
) -> AdaptiveMealRequirement:
    """
    Calculate adaptive meal accounting for the original/default model.

    The original Primary model's snapshotted fat/protein add-on percentage is
    reapplied to actual consumed carbohydrate. The originally derived add-on
    grams are not reused because they were derived from the planned meal.

    Warsaw-derived fat/protein state is not an input to this branch.
    Warsaw-specific result fields therefore remain NULL rather than zero.

    Planned carbohydrate and planned insulin remain excluded.
    """
    consumed_carbs = calculate_actual_consumed_carbs_from_components(
        components=components,
    )

    actual_administered = calculate_actual_administered_insulin(
        dose_events=dose_events,
    )

    if consumed_carbs is None:
        return AdaptiveMealRequirement(
            consumed_carbs_grams=None,
            carb_insulin_requirement_units=None,
            fat_protein_effective_carb_equivalent_grams=None,
            fat_protein_insulin_requirement_units=None,
            total_meal_requirement_units=None,
            actual_administered_units=actual_administered,
            remaining_meal_requirement_units=None,
        )

    addon_percent = Decimal(str(primary_fat_protein_addon_percent or 0))

    if addon_percent < 0:
        raise ValueError("Primary fat/protein add-on cannot be negative")

    effective_carbs = (
        consumed_carbs
        + consumed_carbs * addon_percent / Decimal("100")
    )

    carb_result = calculate_adaptive_carb_requirement(
        consumed_carbs_grams=effective_carbs,
        insulin_to_carb_ratio=insulin_to_carb_ratio,
        actual_administered_units=actual_administered,
    )

    return AdaptiveMealRequirement(
        # Preserve factual actual carbohydrate consumption rather than
        # reporting the Primary model's effective carbohydrate value here.
        consumed_carbs_grams=consumed_carbs,
        carb_insulin_requirement_units=(
            carb_result.carb_insulin_requirement_units
        ),
        fat_protein_effective_carb_equivalent_grams=None,
        fat_protein_insulin_requirement_units=None,
        total_meal_requirement_units=(
            carb_result.carb_insulin_requirement_units
        ),
        actual_administered_units=(
            carb_result.actual_administered_units
        ),
        remaining_meal_requirement_units=(
            carb_result.remaining_units
        ),
    )

def calculate_warsaw_adaptive_meal_requirement_from_state(
    *,
    components,
    fat_protein_effective_carb_equivalent_grams,
    insulin_to_carb_ratio,
    dose_events,
) -> AdaptiveMealRequirement:
    """
    Calculate adaptive meal accounting for the Warsaw v1 alternative model.

    This branch may consume the immutable Warsaw-derived effective
    fat/protein carbohydrate equivalent. It remains independent from the
    original/default primary branch.

    Planned carbohydrate and planned insulin remain excluded.
    """
    return calculate_adaptive_meal_requirement_from_state(
        components=components,
        fat_protein_effective_carb_equivalent_grams=(
            fat_protein_effective_carb_equivalent_grams
        ),
        insulin_to_carb_ratio=insulin_to_carb_ratio,
        dose_events=dose_events,
    )