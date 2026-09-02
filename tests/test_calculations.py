"""
Tests for the Meal -> Calculation transition.
"""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.calculations import (
    _persist_calculation_with_dose_plan,
    _persist_derived_absorption_classification,
    _planned_dose_events_for_calculation,
    _round_units,
)
from app.models import CarbAbsorptionProfile, Meal, MealCalculation


def test_round_units():
    assert _round_units(Decimal("1.234")) == Decimal("1.23")
    assert _round_units(Decimal("1.235")) == Decimal("1.24")


def test_carb_factor_calculation():
    carbohydrate_total = Decimal("60")
    carb_factor = Decimal("10")

    dose = _round_units(
        carbohydrate_total / carb_factor
    )

    assert dose == Decimal("6.00")


def test_carb_factor_changes_calculated_dose():
    carbohydrate_total = Decimal("60")

    breakfast_factor = Decimal("8")
    dinner_factor = Decimal("12")

    breakfast_dose = _round_units(
        carbohydrate_total / breakfast_factor
    )
    dinner_dose = _round_units(
        carbohydrate_total / dinner_factor
    )

    assert breakfast_dose == Decimal("7.50")
    assert dinner_dose == Decimal("5.00")
    assert breakfast_dose != dinner_dose


def test_negative_correction_is_zero():
    glucose = Decimal("100")
    target = Decimal("120")
    isf = Decimal("40")

    correction = _round_units(
        (glucose - target) / isf
    )

    correction = max(correction, Decimal("0"))

    assert correction == Decimal("0.00")

from app.api.calculations import (
    _round_down_to_increment,
    calculate_split_dose,
)


def test_round_down_to_increment_is_conservative():
    assert _round_down_to_increment(Decimal("1.58"), Decimal("0.05")) == Decimal("1.55")
    assert _round_down_to_increment(Decimal("1.58"), Decimal("0.10")) == Decimal("1.50")
    assert _round_down_to_increment(Decimal("1.78"), Decimal("0.50")) == Decimal("1.50")


def test_split_dose_uses_different_icr_at_dose_2_time():
    result = calculate_split_dose(
        carbohydrate_total_grams=80,
        fat_protein_addon_percent=0,
        dose_1_share_percent=60,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=8,
        insulin_rounding_increment_units=0.05,
        glucose_mg_dl=140,
        target_glucose_mg_dl=100,
        meal_isf_mg_dl_per_unit=40,
    )

    assert result.dose_1_carbohydrate_grams == Decimal("48")
    assert result.dose_2_carbohydrate_grams == Decimal("32")
    assert result.correction_dose_units == Decimal("1")
    assert result.dose_1_units == Decimal("5.80")
    assert result.dose_2_units == Decimal("4.00")
    assert result.total_planned_dose_units == Decimal("9.80")


def test_split_dose_correction_never_subtracts():
    result = calculate_split_dose(
        carbohydrate_total_grams=20,
        fat_protein_addon_percent=0,
        dose_1_share_percent=50,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=10,
        insulin_rounding_increment_units=0.05,
        glucose_mg_dl=80,
        target_glucose_mg_dl=100,
        meal_isf_mg_dl_per_unit=40,
    )

    assert result.correction_dose_units == Decimal("0")
    assert result.dose_1_units == Decimal("1.0")
    assert result.dose_2_units == Decimal("1.0")


def test_split_dose_applies_fat_protein_addon_before_split():
    result = calculate_split_dose(
        carbohydrate_total_grams=50,
        fat_protein_addon_percent=20,
        dose_1_share_percent=50,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=10,
        insulin_rounding_increment_units=0.05,
    )

    assert result.fat_protein_addon_grams == Decimal("10")
    assert result.effective_carbohydrate_grams == Decimal("60")
    assert result.dose_1_carbohydrate_grams == Decimal("30")
    assert result.dose_2_carbohydrate_grams == Decimal("30")

def _tracker_test_calculation(*, calculation_id=None):
    return MealCalculation(
        id=calculation_id or uuid4(),
        meal_id=uuid4(),
        patient_id=uuid4(),
        carbohydrate_total_grams=Decimal("10.0"),
        dose_1_units=Decimal("0.500"),
        dose_2_units=Decimal("0.300"),
        dose_2_timestamp=datetime(2026, 9, 2, 11, 55),
        calculation_version="3",
    )


def test_v3_calculation_builds_exactly_two_planned_dose_events():
    meal = Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="test",
        total_carbs_grams=Decimal("10.0"),
    )
    calculation = _tracker_test_calculation()
    calculation.meal_id = meal.id
    calculation.patient_id = meal.patient_id

    events = _planned_dose_events_for_calculation(
        calculation=calculation,
        meal=meal,
    )

    assert len(events) == 2
    assert [event.dose_number for event in events] == [1, 2]
    assert all(event.calculation_id == calculation.id for event in events)
    assert events[0].planned_timestamp == meal.meal_timestamp
    assert events[1].planned_timestamp == calculation.dose_2_timestamp
    assert events[0].planned_units == Decimal("0.500")
    assert events[1].planned_units == Decimal("0.300")
    assert all(event.status == "planned" for event in events)
    assert all(event.actual_timestamp is None for event in events)
    assert all(event.actual_units is None for event in events)
    assert all(event.insulin_event_id is None for event in events)


def test_recalculation_builds_new_tracker_plan_without_mutating_prior_plan():
    meal = Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="test",
        total_carbs_grams=Decimal("10.0"),
    )
    first = _tracker_test_calculation()
    second = _tracker_test_calculation()
    for calculation in (first, second):
        calculation.meal_id = meal.id
        calculation.patient_id = meal.patient_id

    first_events = _planned_dose_events_for_calculation(
        calculation=first,
        meal=meal,
    )
    second_events = _planned_dose_events_for_calculation(
        calculation=second,
        meal=meal,
    )

    assert first.id != second.id
    assert {event.calculation_id for event in first_events} == {first.id}
    assert {event.calculation_id for event in second_events} == {second.id}


class _FailingCommitSession:
    def __init__(self):
        self.added = []
        self.added_all = []
        self.rollback_called = False

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None

    def add_all(self, items):
        self.added_all.extend(items)

    async def commit(self):
        raise SQLAlchemyError("forced tracker persistence failure")

    async def rollback(self):
        self.rollback_called = True

    async def refresh(self, item):
        raise AssertionError("refresh must not run after failed commit")


@pytest.mark.asyncio
async def test_calculation_and_tracker_plan_roll_back_together_on_failure():
    meal = Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="test",
        total_carbs_grams=Decimal("10.0"),
    )
    calculation = _tracker_test_calculation()
    calculation.meal_id = meal.id
    calculation.patient_id = meal.patient_id
    session = _FailingCommitSession()

    with pytest.raises(SQLAlchemyError):
        await _persist_calculation_with_dose_plan(
            db=session,
            calculation=calculation,
            meal=meal,
        )

    assert len(session.added) == 1
    assert len(session.added_all) == 2
    assert session.rollback_called is True


def test_derived_absorption_classification_is_persisted_on_unclassified_meal():
    meal = Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="test",
        total_carbs_grams=Decimal("10.0"),
    )
    profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=meal.patient_id,
        profile_key="medium",
        profile_name="Medium",
        duration_minutes=150,
        absorption_delay_minutes=10,
    )

    changed = _persist_derived_absorption_classification(
        meal=meal,
        absorption_profile=profile,
        classification_source="meal_category_rule_v1",
    )

    assert changed is True
    assert meal.absorption_profile_id == profile.id
    assert meal.absorption_profile_key == "medium"
    assert meal.absorption_classification_source == "meal_category_rule_v1"


def test_derived_absorption_classification_does_not_overwrite_explicit_meal():
    explicit_profile_id = uuid4()
    meal = Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="pizza",
        total_carbs_grams=Decimal("10.0"),
        absorption_profile_id=explicit_profile_id,
        absorption_profile_key="slow",
        absorption_classification_source="manual",
    )
    derived_profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=meal.patient_id,
        profile_key="medium",
        profile_name="Medium",
        duration_minutes=150,
        absorption_delay_minutes=10,
    )

    changed = _persist_derived_absorption_classification(
        meal=meal,
        absorption_profile=derived_profile,
        classification_source="meal_category_rule_v1",
    )

    assert changed is False
    assert meal.absorption_profile_id == explicit_profile_id
    assert meal.absorption_profile_key == "slow"
    assert meal.absorption_classification_source == "manual"
