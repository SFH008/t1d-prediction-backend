from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dose_events import _ensure_planned, _decimal_units
from app.schema.schemas import MealDoseEventAdjust, MealDoseEventConfirm


def event(*, status="planned", insulin_event_id=None):
    return SimpleNamespace(
        dose_number=2,
        status=status,
        insulin_event_id=insulin_event_id,
        planned_units=Decimal("0.300"),
    )


def test_decimal_units_preserves_tracker_precision():
    assert _decimal_units(0.05) == Decimal("0.05")
    assert _decimal_units("0.125") == Decimal("0.125")


def test_planned_event_can_be_finalized():
    _ensure_planned(event())


@pytest.mark.parametrize("status", ["given", "adjusted", "skipped", "cancelled"])
def test_terminal_event_cannot_be_finalized_again(status):
    with pytest.raises(HTTPException) as exc:
        _ensure_planned(event(status=status))
    assert exc.value.status_code == 409


def test_linked_insulin_event_blocks_duplicate_finalization():
    with pytest.raises(HTTPException) as exc:
        _ensure_planned(event(insulin_event_id=uuid4()))
    assert exc.value.status_code == 409


def test_confirm_requires_positive_administered_insulin():
    with pytest.raises(ValidationError):
        MealDoseEventConfirm(
            actual_units=0,
            actual_timestamp=datetime(2026, 9, 2, 11, 55),
        )


def test_adjust_requires_positive_administered_insulin():
    with pytest.raises(ValidationError):
        MealDoseEventAdjust(
            actual_units=0,
            actual_timestamp=datetime(2026, 9, 2, 11, 55),
            adjustment_reason="CGM trending low",
        )
