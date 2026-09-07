from decimal import Decimal

import pytest

from app.services.adaptive_dose import calculate_remaining_insulin_requirement


def test_remaining_requirement_subtracts_actual_administered_insulin():
    result = calculate_remaining_insulin_requirement(
        required_units=Decimal("4.0"),
        actual_administered_units=Decimal("1.5"),
    )

    assert result.required_units == Decimal("4.0")
    assert result.actual_administered_units == Decimal("1.5")
    assert result.remaining_units == Decimal("2.5")


def test_remaining_requirement_is_zero_when_requirement_fully_administered():
    result = calculate_remaining_insulin_requirement(
        required_units=Decimal("4.0"),
        actual_administered_units=Decimal("4.0"),
    )

    assert result.remaining_units == Decimal("0")


def test_remaining_requirement_never_becomes_negative():
    result = calculate_remaining_insulin_requirement(
        required_units=Decimal("4.0"),
        actual_administered_units=Decimal("5.0"),
    )

    assert result.remaining_units == Decimal("0")


def test_no_actual_administration_subtracts_zero():
    result = calculate_remaining_insulin_requirement(
        required_units=Decimal("4.0"),
        actual_administered_units=None,
    )

    assert result.actual_administered_units == Decimal("0")
    assert result.remaining_units == Decimal("4.0")


def test_zero_requirement_stays_zero():
    result = calculate_remaining_insulin_requirement(
        required_units=Decimal("0"),
        actual_administered_units=Decimal("0"),
    )

    assert result.remaining_units == Decimal("0")


def test_negative_required_units_are_rejected():
    try:
        calculate_remaining_insulin_requirement(
            required_units=Decimal("-0.1"),
            actual_administered_units=Decimal("0"),
        )
    except ValueError as exc:
        assert str(exc) == "Required insulin units cannot be negative"
    else:
        raise AssertionError("Expected ValueError")


def test_negative_actual_administered_units_are_rejected():
    try:
        calculate_remaining_insulin_requirement(
            required_units=Decimal("4.0"),
            actual_administered_units=Decimal("-0.1"),
        )
    except ValueError as exc:
        assert str(exc) == "Actual administered insulin units cannot be negative"
    else:
        raise AssertionError("Expected ValueError")

def test_actual_consumed_carbs_sums_known_component_consumption():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    result = calculate_actual_consumed_carbs(
        consumed_carbs_grams=[
            Decimal("15.0"),
            Decimal("7.5"),
            Decimal("2.5"),
        ]
    )

    assert result == Decimal("25.0")


def test_explicit_zero_consumption_is_known_zero():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    result = calculate_actual_consumed_carbs(
        consumed_carbs_grams=[
            Decimal("0"),
            Decimal("0"),
        ]
    )

    assert result == Decimal("0")


def test_unknown_component_consumption_keeps_meal_consumption_unknown():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    result = calculate_actual_consumed_carbs(
        consumed_carbs_grams=[
            Decimal("15.0"),
            None,
        ]
    )

    assert result is None


def test_all_unknown_component_consumption_is_unknown():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    result = calculate_actual_consumed_carbs(
        consumed_carbs_grams=[
            None,
            None,
        ]
    )

    assert result is None


def test_empty_component_list_is_unknown():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    result = calculate_actual_consumed_carbs(
        consumed_carbs_grams=[]
    )

    assert result is None


def test_negative_consumed_carbs_are_rejected():
    from app.services.adaptive_dose import calculate_actual_consumed_carbs

    try:
        calculate_actual_consumed_carbs(
            consumed_carbs_grams=[
                Decimal("10.0"),
                Decimal("-0.1"),
            ]
        )
    except ValueError as exc:
        assert str(exc) == "Consumed carbohydrate grams cannot be negative"
    else:
        raise AssertionError("Expected ValueError")

def test_carb_insulin_requirement_uses_actual_consumed_carbs_and_icr():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    result = calculate_carb_insulin_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
    )

    assert result == Decimal("3.0")


def test_carb_insulin_requirement_zero_carbs_is_zero():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    result = calculate_carb_insulin_requirement(
        consumed_carbs_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10.0"),
    )

    assert result == Decimal("0")


def test_carb_insulin_requirement_unknown_consumption_is_unknown():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    result = calculate_carb_insulin_requirement(
        consumed_carbs_grams=None,
        insulin_to_carb_ratio=Decimal("10.0"),
    )

    assert result is None


def test_carb_insulin_requirement_rejects_negative_consumed_carbs():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    try:
        calculate_carb_insulin_requirement(
            consumed_carbs_grams=Decimal("-0.1"),
            insulin_to_carb_ratio=Decimal("10.0"),
        )
    except ValueError as exc:
        assert str(exc) == "Consumed carbohydrate grams cannot be negative"
    else:
        raise AssertionError("Expected ValueError")


def test_carb_insulin_requirement_rejects_zero_icr():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    try:
        calculate_carb_insulin_requirement(
            consumed_carbs_grams=Decimal("30.0"),
            insulin_to_carb_ratio=Decimal("0"),
        )
    except ValueError as exc:
        assert str(exc) == "Insulin-to-carbohydrate ratio must be greater than zero"
    else:
        raise AssertionError("Expected ValueError")


def test_carb_insulin_requirement_rejects_negative_icr():
    from app.services.adaptive_dose import calculate_carb_insulin_requirement

    try:
        calculate_carb_insulin_requirement(
            consumed_carbs_grams=Decimal("30.0"),
            insulin_to_carb_ratio=Decimal("-1.0"),
        )
    except ValueError as exc:
        assert str(exc) == "Insulin-to-carbohydrate ratio must be greater than zero"
    else:
        raise AssertionError("Expected ValueError")

def test_adaptive_carb_requirement_combines_consumption_icr_and_actual_insulin():
    from app.services.adaptive_dose import calculate_adaptive_carb_requirement

    result = calculate_adaptive_carb_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("1.0"),
    )

    assert result.consumed_carbs_grams == Decimal("30.0")
    assert result.carb_insulin_requirement_units == Decimal("3.0")
    assert result.actual_administered_units == Decimal("1.0")
    assert result.remaining_units == Decimal("2.0")


def test_adaptive_carb_requirement_unknown_consumption_stays_unknown():
    from app.services.adaptive_dose import calculate_adaptive_carb_requirement

    result = calculate_adaptive_carb_requirement(
        consumed_carbs_grams=None,
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("1.0"),
    )

    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None
    assert result.remaining_units is None


def test_adaptive_carb_requirement_zero_consumption_yields_zero_remaining():
    from app.services.adaptive_dose import calculate_adaptive_carb_requirement

    result = calculate_adaptive_carb_requirement(
        consumed_carbs_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("0"),
    )

    assert result.carb_insulin_requirement_units == Decimal("0")
    assert result.remaining_units == Decimal("0")


def test_adaptive_carb_requirement_caps_negative_remaining_at_zero():
    from app.services.adaptive_dose import calculate_adaptive_carb_requirement

    result = calculate_adaptive_carb_requirement(
        consumed_carbs_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("3.0"),
    )

    assert result.carb_insulin_requirement_units == Decimal("2.0")
    assert result.remaining_units == Decimal("0")

def test_fat_protein_insulin_requirement_uses_effective_equivalent_and_icr():
    from app.services.adaptive_dose import (
        calculate_fat_protein_insulin_requirement,
    )

    result = calculate_fat_protein_insulin_requirement(
        effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
    )

    assert result == Decimal("2.0")


def test_fat_protein_insulin_requirement_zero_effective_contribution_is_zero():
    from app.services.adaptive_dose import (
        calculate_fat_protein_insulin_requirement,
    )

    result = calculate_fat_protein_insulin_requirement(
        effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10.0"),
    )

    assert result == Decimal("0")


def test_fat_protein_insulin_requirement_rejects_negative_effective_equivalent():
    from app.services.adaptive_dose import (
        calculate_fat_protein_insulin_requirement,
    )

    try:
        calculate_fat_protein_insulin_requirement(
            effective_carb_equivalent_grams=Decimal("-0.1"),
            insulin_to_carb_ratio=Decimal("10.0"),
        )
    except ValueError as exc:
        assert str(exc) == (
            "Effective fat/protein carbohydrate equivalent cannot be negative"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_fat_protein_insulin_requirement_rejects_zero_icr():
    from app.services.adaptive_dose import (
        calculate_fat_protein_insulin_requirement,
    )

    try:
        calculate_fat_protein_insulin_requirement(
            effective_carb_equivalent_grams=Decimal("20.0"),
            insulin_to_carb_ratio=Decimal("0"),
        )
    except ValueError as exc:
        assert str(exc) == (
            "Insulin-to-carbohydrate ratio must be greater than zero"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_fat_protein_insulin_requirement_rejects_negative_icr():
    from app.services.adaptive_dose import (
        calculate_fat_protein_insulin_requirement,
    )

    try:
        calculate_fat_protein_insulin_requirement(
            effective_carb_equivalent_grams=Decimal("20.0"),
            insulin_to_carb_ratio=Decimal("-1.0"),
        )
    except ValueError as exc:
        assert str(exc) == (
            "Insulin-to-carbohydrate ratio must be greater than zero"
        )
    else:
        raise AssertionError("Expected ValueError")

def test_adaptive_meal_requirement_combines_carb_and_fat_protein_requirements():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("1.5"),
    )

    assert result.consumed_carbs_grams == Decimal("30.0")
    assert result.carb_insulin_requirement_units == Decimal("3.0")

    assert (
        result.fat_protein_effective_carb_equivalent_grams
        == Decimal("20.0")
    )
    assert result.fat_protein_insulin_requirement_units == Decimal("2.0")

    assert result.total_meal_requirement_units == Decimal("5.0")
    assert result.actual_administered_units == Decimal("1.5")
    assert result.remaining_meal_requirement_units == Decimal("3.5")


def test_adaptive_meal_requirement_zero_fp_preserves_carb_requirement():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("1.0"),
    )

    assert result.carb_insulin_requirement_units == Decimal("3.0")
    assert result.fat_protein_insulin_requirement_units == Decimal("0")
    assert result.total_meal_requirement_units == Decimal("3.0")
    assert result.remaining_meal_requirement_units == Decimal("2.0")


def test_adaptive_meal_requirement_unknown_consumption_stays_unknown():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=None,
        fat_protein_effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("1.0"),
    )

    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None

    # FP remains independently known.
    assert result.fat_protein_insulin_requirement_units == Decimal("2.0")

    # But the complete meal requirement cannot be claimed as known.
    assert result.total_meal_requirement_units is None
    assert result.remaining_meal_requirement_units is None


def test_adaptive_meal_requirement_zero_consumption_can_still_have_fp_requirement():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=Decimal("0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("0"),
    )

    assert result.carb_insulin_requirement_units == Decimal("0")
    assert result.fat_protein_insulin_requirement_units == Decimal("2.0")
    assert result.total_meal_requirement_units == Decimal("2.0")
    assert result.remaining_meal_requirement_units == Decimal("2.0")


def test_adaptive_meal_requirement_subtracts_only_actual_administered_insulin():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=None,
    )

    assert result.total_meal_requirement_units == Decimal("5.0")
    assert result.actual_administered_units == Decimal("0")
    assert result.remaining_meal_requirement_units == Decimal("5.0")


def test_adaptive_meal_requirement_never_returns_negative_remaining():
    from app.services.adaptive_dose import calculate_adaptive_meal_requirement

    result = calculate_adaptive_meal_requirement(
        consumed_carbs_grams=Decimal("30.0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20.0"),
        insulin_to_carb_ratio=Decimal("10.0"),
        actual_administered_units=Decimal("6.0"),
    )

    assert result.total_meal_requirement_units == Decimal("5.0")
    assert result.remaining_meal_requirement_units == Decimal("0")

def test_actual_administered_insulin_sums_given_and_adjusted_events():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    result = calculate_actual_administered_insulin(
        dose_events=[
            {
                "status": "given",
                "planned_units": Decimal("2.0"),
                "actual_units": Decimal("2.0"),
            },
            {
                "status": "adjusted",
                "planned_units": Decimal("3.0"),
                "actual_units": Decimal("1.5"),
            },
        ]
    )

    assert result == Decimal("3.5")


def test_actual_administered_insulin_never_uses_planned_units():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    result = calculate_actual_administered_insulin(
        dose_events=[
            {
                "status": "planned",
                "planned_units": Decimal("4.0"),
                "actual_units": None,
            },
        ]
    )

    assert result == Decimal("0")


def test_actual_administered_insulin_ignores_skipped_and_cancelled_events():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    result = calculate_actual_administered_insulin(
        dose_events=[
            {
                "status": "skipped",
                "planned_units": Decimal("2.0"),
                "actual_units": None,
            },
            {
                "status": "cancelled",
                "planned_units": Decimal("3.0"),
                "actual_units": None,
            },
        ]
    )

    assert result == Decimal("0")


def test_actual_administered_insulin_empty_event_list_is_zero():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    result = calculate_actual_administered_insulin(
        dose_events=[]
    )

    assert result == Decimal("0")


def test_actual_administered_insulin_rejects_terminal_administered_event_without_units():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    try:
        calculate_actual_administered_insulin(
            dose_events=[
                {
                    "status": "given",
                    "planned_units": Decimal("2.0"),
                    "actual_units": None,
                },
            ]
        )
    except ValueError as exc:
        assert str(exc) == (
            "Administered dose event must have actual insulin units"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_actual_administered_insulin_rejects_negative_actual_units():
    from app.services.adaptive_dose import calculate_actual_administered_insulin

    try:
        calculate_actual_administered_insulin(
            dose_events=[
                {
                    "status": "adjusted",
                    "planned_units": Decimal("2.0"),
                    "actual_units": Decimal("-0.1"),
                },
            ]
        )
    except ValueError as exc:
        assert str(exc) == (
            "Actual administered insulin units cannot be negative"
        )
    else:
        raise AssertionError("Expected ValueError")

def test_actual_consumed_carbs_from_components_sums_persisted_actual_values():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    result = calculate_actual_consumed_carbs_from_components(
        components=[
            {
                "carbs_grams": Decimal("15.0"),
                "consumed_carbs_grams": Decimal("7.5"),
            },
            {
                "carbs_grams": Decimal("10.0"),
                "consumed_carbs_grams": Decimal("4.0"),
            },
        ]
    )

    assert result == Decimal("11.5")


def test_actual_consumed_carbs_from_components_preserves_explicit_zero():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    result = calculate_actual_consumed_carbs_from_components(
        components=[
            {
                "carbs_grams": Decimal("15.0"),
                "consumed_carbs_grams": Decimal("0"),
            },
            {
                "carbs_grams": Decimal("10.0"),
                "consumed_carbs_grams": Decimal("0"),
            },
        ]
    )

    assert result == Decimal("0")


def test_actual_consumed_carbs_from_components_unknown_component_makes_meal_unknown():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    result = calculate_actual_consumed_carbs_from_components(
        components=[
            {
                "carbs_grams": Decimal("15.0"),
                "consumed_carbs_grams": Decimal("7.5"),
            },
            {
                "carbs_grams": Decimal("10.0"),
                "consumed_carbs_grams": None,
            },
        ]
    )

    assert result is None


def test_actual_consumed_carbs_from_components_never_falls_back_to_planned_carbs():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    result = calculate_actual_consumed_carbs_from_components(
        components=[
            {
                "carbs_grams": Decimal("50.0"),
                "consumed_carbs_grams": None,
            },
        ]
    )

    # Planned 50 g must not be interpreted as actual consumption.
    assert result is None


def test_actual_consumed_carbs_from_components_empty_meal_is_unknown():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    result = calculate_actual_consumed_carbs_from_components(
        components=[]
    )

    assert result is None


def test_actual_consumed_carbs_from_components_rejects_negative_actual_value():
    from app.services.adaptive_dose import (
        calculate_actual_consumed_carbs_from_components,
    )

    with pytest.raises(
        ValueError,
        match="Consumed carbohydrate grams cannot be negative",
    ):
        calculate_actual_consumed_carbs_from_components(
            components=[
                {
                    "carbs_grams": Decimal("15.0"),
                    "consumed_carbs_grams": Decimal("-1.0"),
                },
            ]
        )

def test_adaptive_meal_requirement_from_state_composes_persisted_inputs():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("20"),
                "consumed_carbs_grams": Decimal("15"),
            },
            {
                "carbs_grams": Decimal("20"),
                "consumed_carbs_grams": Decimal("15"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("20"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[
            {
                "status": "given",
                "planned_units": Decimal("3"),
                "actual_units": Decimal("1.5"),
            },
        ],
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3")
    assert (
        result.fat_protein_effective_carb_equivalent_grams
        == Decimal("20")
    )
    assert result.fat_protein_insulin_requirement_units == Decimal("2")
    assert result.total_meal_requirement_units == Decimal("5")
    assert result.actual_administered_units == Decimal("1.5")
    assert result.remaining_meal_requirement_units == Decimal("3.5")


def test_adaptive_meal_requirement_from_state_never_uses_planned_carbs():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("60"),
                "consumed_carbs_grams": None,
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
    )

    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None
    assert result.total_meal_requirement_units is None
    assert result.remaining_meal_requirement_units is None


def test_adaptive_meal_requirement_from_state_never_uses_planned_insulin():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("30"),
                "consumed_carbs_grams": Decimal("30"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[
            {
                "status": "planned",
                "planned_units": Decimal("3"),
                "actual_units": None,
            },
        ],
    )

    assert result.total_meal_requirement_units == Decimal("3")
    assert result.actual_administered_units == Decimal("0")
    assert result.remaining_meal_requirement_units == Decimal("3")


def test_adaptive_meal_requirement_from_state_sums_multiple_actual_doses():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("50"),
                "consumed_carbs_grams": Decimal("50"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("10"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[
            {
                "status": "given",
                "planned_units": Decimal("2"),
                "actual_units": Decimal("2"),
            },
            {
                "status": "adjusted",
                "planned_units": Decimal("3"),
                "actual_units": Decimal("1"),
            },
        ],
    )

    # 50 g carbs / 10 = 5 U
    # 10 g effective FP / 10 = 1 U
    # 3 U actually administered
    assert result.total_meal_requirement_units == Decimal("6")
    assert result.actual_administered_units == Decimal("3")
    assert result.remaining_meal_requirement_units == Decimal("3")


def test_adaptive_meal_requirement_from_state_explicit_zero_consumption_is_known():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("30"),
                "consumed_carbs_grams": Decimal("0"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
    )

    assert result.consumed_carbs_grams == Decimal("0")
    assert result.total_meal_requirement_units == Decimal("0")
    assert result.remaining_meal_requirement_units == Decimal("0")


def test_adaptive_meal_requirement_from_state_caps_overadministration_at_zero():
    from app.services.adaptive_dose import (
        calculate_adaptive_meal_requirement_from_state,
    )

    result = calculate_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("20"),
                "consumed_carbs_grams": Decimal("20"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[
            {
                "status": "given",
                "planned_units": Decimal("4"),
                "actual_units": Decimal("4"),
            },
        ],
    )

    assert result.total_meal_requirement_units == Decimal("2")
    assert result.actual_administered_units == Decimal("4")
    assert result.remaining_meal_requirement_units == Decimal("0")

def test_adaptive_meal_calculation_model_exists():
    from app.models import AdaptiveMealCalculation

    assert AdaptiveMealCalculation.__tablename__ == "adaptive_meal_calculations"


def test_adaptive_meal_calculation_model_has_lineage_columns():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert "id" in columns
    assert "patient_id" in columns
    assert "meal_id" in columns
    assert "calculation_id" in columns
    assert "calculated_at" in columns


def test_adaptive_meal_calculation_model_has_input_snapshot_columns():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert "consumed_carbs_grams" in columns
    assert "fat_protein_effective_carb_equivalent_grams" in columns
    assert "insulin_to_carb_ratio" in columns
    assert "actual_administered_units" in columns


def test_adaptive_meal_calculation_model_has_requirement_columns():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert "carb_insulin_requirement_units" in columns
    assert "fat_protein_insulin_requirement_units" in columns
    assert "total_meal_requirement_units" in columns
    assert "remaining_meal_requirement_units" in columns


def test_adaptive_meal_calculation_model_has_version_column():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert "adaptive_calculation_version" in columns


def test_adaptive_meal_calculation_model_preserves_unknown_consumption_nullability():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert columns["consumed_carbs_grams"].nullable is True
    assert columns["carb_insulin_requirement_units"].nullable is True
    assert columns["total_meal_requirement_units"].nullable is True
    assert columns["remaining_meal_requirement_units"].nullable is True


def test_adaptive_meal_calculation_model_requires_known_nonnullable_snapshots():
    from app.models import AdaptiveMealCalculation

    columns = AdaptiveMealCalculation.__table__.columns

    assert columns["insulin_to_carb_ratio"].nullable is False
    assert columns["actual_administered_units"].nullable is False
    assert columns["adaptive_calculation_version"].nullable is False
    assert columns["adaptive_model_version"].nullable is False


def test_adaptive_meal_calculation_allows_multiple_rows_per_calculation():
    from app.models import AdaptiveMealCalculation

    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in AdaptiveMealCalculation.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("calculation_id",) not in unique_column_sets

def test_primary_adaptive_requirement_is_independent_of_warsaw_contribution():
    """
    The original/default adaptive model must not consume Warsaw-derived
    fat/protein carbohydrate equivalent.

    Warsaw is an alternative model, not an input to the primary model.
    """
    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    components = [
        {
            "carbs_grams": Decimal("30"),
            "consumed_carbs_grams": Decimal("30"),
        },
    ]

    dose_events = [
        {
            "status": "given",
            "planned_units": Decimal("2"),
            "actual_units": Decimal("1"),
        },
    ]

    without_warsaw = calculate_primary_adaptive_meal_requirement_from_state(
        components=components,
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=dose_events,
        primary_fat_protein_addon_percent=Decimal("0"),
    )

    # Deliberately no Warsaw argument exists on the primary calculation.
    assert without_warsaw.consumed_carbs_grams == Decimal("30")
    assert without_warsaw.carb_insulin_requirement_units == Decimal("3")
    assert without_warsaw.total_meal_requirement_units == Decimal("3")
    assert without_warsaw.actual_administered_units == Decimal("1")
    assert without_warsaw.remaining_meal_requirement_units == Decimal("2")


def test_warsaw_adaptive_requirement_remains_independent_alternative():
    """
    Warsaw may include its own effective FP contribution without changing
    the semantics of the primary adaptive model.
    """
    from app.services.adaptive_dose import (
        calculate_warsaw_adaptive_meal_requirement_from_state,
    )

    result = calculate_warsaw_adaptive_meal_requirement_from_state(
        components=[
            {
                "carbs_grams": Decimal("30"),
                "consumed_carbs_grams": Decimal("30"),
            },
        ],
        fat_protein_effective_carb_equivalent_grams=Decimal("20"),
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[
            {
                "status": "given",
                "planned_units": Decimal("2"),
                "actual_units": Decimal("1"),
            },
        ],
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3")
    assert result.fat_protein_insulin_requirement_units == Decimal("2")
    assert result.total_meal_requirement_units == Decimal("5")
    assert result.actual_administered_units == Decimal("1")
    assert result.remaining_meal_requirement_units == Decimal("4")

def test_adaptive_meal_calculation_model_has_model_provenance_column():
    from app.models import AdaptiveMealCalculation

    assert hasattr(
        AdaptiveMealCalculation,
        "adaptive_model_version",
    )


def test_adaptive_meal_calculation_model_allows_warsaw_fields_to_be_null():
    from app.models import AdaptiveMealCalculation

    table = AdaptiveMealCalculation.__table__

    assert (
        table.c.fat_protein_effective_carb_equivalent_grams.nullable
        is True
    )
    assert (
        table.c.fat_protein_insulin_requirement_units.nullable
        is True
    )

def test_primary_adaptive_zero_addon_uses_actual_consumed_carbs_only():
    """Primary 0% FP add-on leaves actual consumed carbohydrate unchanged."""
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("0"),
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3")
    assert result.total_meal_requirement_units == Decimal("3")
    assert result.remaining_meal_requirement_units == Decimal("3")

    # Warsaw-specific outputs must never be populated by Primary.
    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None


def test_primary_adaptive_applies_primary_addon_to_actual_consumed_carbs():
    """
    Primary adaptive accounting reapplies the snapshotted Primary FP percentage
    to actual consumption.

    30 g actually consumed + 20% Primary add-on = 36 g effective carbs.
    At ICR 10 g/U this is a 3.6 U meal requirement.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3.6")
    assert result.total_meal_requirement_units == Decimal("3.6")
    assert result.remaining_meal_requirement_units == Decimal("3.6")

    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None


def test_primary_adaptive_addon_is_based_on_actual_not_original_planned_carbs():
    """
    The original Primary percentage is preserved, but its originally derived
    add-on grams are not reused.

    Original plan could have been 50 g with a 20% add-on (= 10 g).
    If only 30 g are actually consumed, adaptive Primary must use:
        30 g + 20% = 36 g
    not:
        30 g + original 10 g = 40 g.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.total_meal_requirement_units == Decimal("3.6")
    assert result.total_meal_requirement_units != Decimal("4")


def test_primary_adaptive_unknown_consumption_remains_unknown_with_addon():
    """
    A Primary FP percentage must not turn unknown consumption into a known
    requirement.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": None},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None
    assert result.total_meal_requirement_units is None
    assert result.remaining_meal_requirement_units is None

    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None


def test_primary_adaptive_zero_addon_uses_actual_consumed_carbs_only():
    """Primary 0% FP add-on leaves actual consumed carbohydrate unchanged."""
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("0"),
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3")
    assert result.total_meal_requirement_units == Decimal("3")
    assert result.remaining_meal_requirement_units == Decimal("3")

    # Warsaw-specific outputs must never be populated by Primary.
    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None


def test_primary_adaptive_applies_primary_addon_to_actual_consumed_carbs():
    """
    Primary adaptive accounting reapplies the snapshotted Primary FP percentage
    to actual consumption.

    30 g actually consumed + 20% Primary add-on = 36 g effective carbs.
    At ICR 10 g/U this is a 3.6 U meal requirement.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3.6")
    assert result.total_meal_requirement_units == Decimal("3.6")
    assert result.remaining_meal_requirement_units == Decimal("3.6")

    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None


def test_primary_adaptive_addon_is_based_on_actual_not_original_planned_carbs():
    """
    The original Primary percentage is preserved, but its originally derived
    add-on grams are not reused.

    Original plan could have been 50 g with a 20% add-on (= 10 g).
    If only 30 g are actually consumed, adaptive Primary must use:
        30 g + 20% = 36 g
    not:
        30 g + original 10 g = 40 g.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": Decimal("30")},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.total_meal_requirement_units == Decimal("3.6")
    assert result.total_meal_requirement_units != Decimal("4")


def test_primary_adaptive_unknown_consumption_remains_unknown_with_addon():
    """
    A Primary FP percentage must not turn unknown consumption into a known
    requirement.
    """
    from decimal import Decimal

    from app.services.adaptive_dose import (
        calculate_primary_adaptive_meal_requirement_from_state,
    )

    result = calculate_primary_adaptive_meal_requirement_from_state(
        components=[
            {"consumed_carbs_grams": None},
        ],
        insulin_to_carb_ratio=Decimal("10"),
        dose_events=[],
        primary_fat_protein_addon_percent=Decimal("20"),
    )

    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None
    assert result.total_meal_requirement_units is None
    assert result.remaining_meal_requirement_units is None

    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None
