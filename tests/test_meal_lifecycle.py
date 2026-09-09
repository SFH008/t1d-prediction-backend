"""
Tests for the patient-scoped meal lifecycle.

Meal lifecycle is durable backend state. The patient Expo application must
never infer an active meal from local navigation or component state.
"""

from datetime import datetime
from uuid import uuid4

from app.models import Meal


def meal(*, patient_id=None, status="captured"):
    return Meal(
        id=uuid4(),
        patient_id=patient_id or uuid4(),
        meal_timestamp=datetime(2026, 9, 8, 12, 0),
        meal_category="lunch",
        status=status,
        total_carbs_grams=60,
        source="manual",
    )


def test_meal_lifecycle_model_has_explicit_started_at():
    value = meal()

    assert hasattr(value, "started_at")
    assert value.started_at is None


def test_meal_start_timestamp_is_distinct_from_planning_timestamp():
    value = meal()

    started_at = datetime(2026, 9, 8, 12, 35)

    value.started_at = started_at
    value.status = "active"

    assert value.meal_timestamp == datetime(2026, 9, 8, 12, 0)
    assert value.started_at == started_at
    assert value.status == "active"


def test_active_meal_is_patient_specific():
    patient_a = uuid4()
    patient_b = uuid4()

    meal_a = meal(patient_id=patient_a, status="active")
    meal_b = meal(patient_id=patient_b, status="active")

    assert meal_a.patient_id == patient_a
    assert meal_b.patient_id == patient_b
    assert meal_a.patient_id != meal_b.patient_id


def test_patient_identity_is_not_derived_from_meal_identity():
    patient_a = uuid4()
    patient_b = uuid4()

    value = meal(patient_id=patient_a)

    assert value.patient_id == patient_a
    assert value.patient_id != patient_b