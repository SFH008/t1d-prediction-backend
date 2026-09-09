"""
Tests for backend-owned meal lifecycle transitions.
"""

from datetime import datetime
from uuid import uuid4

import pytest

from app.models import Meal, MealCarbGroup
from app.services.meal_lifecycle import (
    MealLifecycleError,
    complete_meal_if_recorded,
    is_meal_recording_complete,
    start_meal,
)


def meal(*, status="captured", started_at=None):
    return Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 8, 12, 0),
        meal_category="lunch",
        status=status,
        started_at=started_at,
        total_carbs_grams=60,
        source="manual",
    )


def test_start_meal_transitions_captured_meal_to_active():
    value = meal()
    actual_start = datetime(2026, 9, 8, 12, 35)

    result = start_meal(
        value,
        started_at=actual_start,
    )

    assert result is value
    assert value.status == "active"
    assert value.started_at == actual_start


def test_start_meal_does_not_change_planning_timestamp():
    value = meal()
    planning_timestamp = value.meal_timestamp

    start_meal(
        value,
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    assert value.meal_timestamp == planning_timestamp


def test_active_meal_cannot_be_started_again():
    value = meal(
        status="active",
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    with pytest.raises(
        MealLifecycleError,
        match="cannot be started",
    ):
        start_meal(
            value,
            started_at=datetime(2026, 9, 8, 12, 40),
        )


def test_captured_meal_with_existing_started_at_is_rejected():
    value = meal(
        status="captured",
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    with pytest.raises(
        MealLifecycleError,
        match="already has a started_at",
    ):
        start_meal(
            value,
            started_at=datetime(2026, 9, 8, 12, 40),
        )



class _Dose:
    def __init__(self, status):
        self.status = status


def _active_meal_with_consumption(*values):
    meal = Meal()
    meal.status = "active"

    for index, value in enumerate(
        values,
        start=1,
    ):
        meal.carb_groups.append(
            MealCarbGroup(
                group_number=index,
                group_key=f"group-{index}",
                group_name=f"Group {index}",
                quantity_grams=10,
                carb_factor_g_per_g=1,
                carbs_grams=10,
                consumed_quantity_grams=value,
                consumed_carbs_grams=value,
            )
        )

    return meal


def test_completed_meal_requires_known_consumption():
    meal = _active_meal_with_consumption(
        8,
        None,
    )

    assert not is_meal_recording_complete(
        meal,
        dose_events=[
            _Dose("given"),
            _Dose("skipped"),
        ],
    )


def test_explicit_zero_consumption_is_known():
    meal = _active_meal_with_consumption(
        8,
        0,
    )

    assert is_meal_recording_complete(
        meal,
        dose_events=[
            _Dose("given"),
            _Dose("skipped"),
        ],
    )


def test_completed_meal_requires_all_doses_resolved():
    meal = _active_meal_with_consumption(
        8,
        0,
    )

    assert not is_meal_recording_complete(
        meal,
        dose_events=[
            _Dose("given"),
            _Dose("planned"),
        ],
    )


def test_cancelled_dose_does_not_complete_meal():
    meal = _active_meal_with_consumption(
        8,
        0,
    )

    assert not is_meal_recording_complete(
        meal,
        dose_events=[
            _Dose("given"),
            _Dose("cancelled"),
        ],
    )


def test_given_adjusted_and_skipped_are_completion_states():
    for statuses in (
        ["given", "given"],
        ["adjusted", "skipped"],
        ["skipped", "given"],
    ):
        meal = _active_meal_with_consumption(
            8,
            0,
        )

        assert is_meal_recording_complete(
            meal,
            dose_events=[
                _Dose(status)
                for status in statuses
            ],
        )


def test_complete_meal_if_recorded_transitions_active_to_completed():
    meal = _active_meal_with_consumption(
        8,
        0,
    )

    changed = complete_meal_if_recorded(
        meal,
        dose_events=[
            _Dose("skipped"),
            _Dose("given"),
        ],
    )

    assert changed is True
    assert meal.status == "completed"


def test_incomplete_meal_remains_active():
    meal = _active_meal_with_consumption(
        8,
        None,
    )

    changed = complete_meal_if_recorded(
        meal,
        dose_events=[
            _Dose("skipped"),
            _Dose("given"),
        ],
    )

    assert changed is False
    assert meal.status == "active"
