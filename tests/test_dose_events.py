from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import MealDoseEvent
from app.schema.schemas import (
    MealDoseEventAdjust,
    MealDoseEventConfirm,
    MealDoseEventResponse,
    MealDoseEventSkip,
)


def test_meal_dose_event_model_tracks_plan_without_mutating_calculation():
    event = MealDoseEvent(
        patient_id=uuid4(),
        meal_id=uuid4(),
        calculation_id=uuid4(),
        dose_number=2,
        planned_timestamp=datetime(2026, 9, 2, 11, 55),
        planned_units=Decimal("0.300"),
        status="planned",
    )

    assert event.dose_number == 2
    assert event.planned_units == Decimal("0.300")
    assert event.actual_units is None


def test_confirm_schema_requires_non_negative_actual_units():
    item = MealDoseEventConfirm(
        actual_units=0.3,
        actual_timestamp=datetime(2026, 9, 2, 11, 55),
    )
    assert item.actual_units == 0.3

    with pytest.raises(ValidationError):
        MealDoseEventConfirm(
            actual_units=-0.1,
            actual_timestamp=datetime(2026, 9, 2, 11, 55),
        )


def test_adjust_schema_requires_reason():
    with pytest.raises(ValidationError):
        MealDoseEventAdjust(
            actual_units=0.2,
            actual_timestamp=datetime(2026, 9, 2, 11, 55),
            adjustment_reason="",
        )


def test_skip_schema_requires_reason():
    item = MealDoseEventSkip(adjustment_reason="Meal not fully eaten")
    assert item.adjustment_reason == "Meal not fully eaten"


def test_response_schema_accepts_tracker_snapshot():
    response = MealDoseEventResponse(
        id=uuid4(),
        patient_id=uuid4(),
        meal_id=uuid4(),
        calculation_id=uuid4(),
        dose_number=1,
        planned_timestamp=datetime(2026, 9, 2, 10, 40),
        planned_units=0.5,
        status="planned",
        created_at=datetime(2026, 9, 2, 10, 39),
        updated_at=datetime(2026, 9, 2, 10, 39),
    )
    assert response.status == "planned"
    assert response.actual_units is None


def test_confirm_schema_does_not_invent_delivery_method():
    item = MealDoseEventConfirm(
        actual_units=0.3,
        actual_timestamp=datetime(2026, 9, 2, 11, 55),
    )

    assert item.delivery_method is None


def test_adjust_schema_does_not_invent_delivery_method():
    item = MealDoseEventAdjust(
        actual_units=0.2,
        actual_timestamp=datetime(2026, 9, 2, 11, 55),
        adjustment_reason="Partial meal",
    )

    assert item.delivery_method is None


def test_utc_naive_converts_aware_timestamp():
    from datetime import datetime, timezone

    from app.api.dose_events import _utc_naive

    value = datetime(2026, 9, 8, 13, 38, 49, tzinfo=timezone.utc)

    result = _utc_naive(value)

    assert result == datetime(2026, 9, 8, 13, 38, 49)
    assert result.tzinfo is None


def test_utc_naive_preserves_naive_timestamp():
    from datetime import datetime

    from app.api.dose_events import _utc_naive

    value = datetime(2026, 9, 8, 13, 38, 49)

    result = _utc_naive(value)

    assert result == value
    assert result.tzinfo is None
