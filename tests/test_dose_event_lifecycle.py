from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dose_events import _load_dose_event


def result_returning(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_load_dose_event_rejects_execution_for_captured_meal():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = SimpleNamespace(
        id=calculation_id,
        patient_id=patient_id,
        meal_id=meal_id,
    )
    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="captured",
    )
    event = SimpleNamespace(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=1,
        status="planned",
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                result_returning(calculation),
                result_returning(meal),
                result_returning(event),
            ]
        )
    )

    with pytest.raises(HTTPException) as exc:
        await _load_dose_event(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            dose_number=1,
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "Dose execution can only be recorded for an active meal"
    )


@pytest.mark.asyncio
async def test_load_dose_event_allows_execution_for_active_meal():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = SimpleNamespace(
        id=calculation_id,
        patient_id=patient_id,
        meal_id=meal_id,
    )
    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
    )
    event = SimpleNamespace(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=1,
        status="planned",
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                result_returning(calculation),
                result_returning(meal),
                result_returning(event),
            ]
        )
    )

    loaded = await _load_dose_event(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        dose_number=1,
        db=db,
    )

    assert loaded is event
