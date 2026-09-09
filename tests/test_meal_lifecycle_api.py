"""
Tests for the patient-scoped meal lifecycle API.

The backend is authoritative for active-meal state:
- a patient may have at most one active meal;
- different patients may have independent active meals;
- the client retrieves active state from the backend.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.meals import (
    get_active_patient_meal,
    start_patient_meal,
)
from app.models import Meal


def meal(*, patient_id, status="captured", started_at=None):
    return Meal(
        id=uuid4(),
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 8, 12, 0),
        meal_category="lunch",
        status=status,
        started_at=started_at,
        total_carbs_grams=60,
        source="manual",
    )


def database_returning(*values):
    """
    Build an AsyncSession-style test double.

    AsyncSession.execute() is asynchronous, while the Result methods returned
    by execute() are synchronous.
    """
    db = AsyncMock()

    results = []
    for value in values:
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        results.append(result)

    db.execute.side_effect = results

    return db


@pytest.mark.asyncio
async def test_start_endpoint_persists_active_meal():
    patient_id = uuid4()
    value = meal(patient_id=patient_id)
    original_timestamp = value.meal_timestamp

    # Query 1: patient-scoped meal.
    # Query 2: another active meal for this patient.
    db = database_returning(value, None)

    result = await start_patient_meal(
        patient_id=patient_id,
        meal_id=value.id,
        db=db,
    )

    assert result is value
    assert value.status == "active"
    assert value.started_at is not None
    assert value.meal_timestamp == original_timestamp

    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(value)


@pytest.mark.asyncio
async def test_start_endpoint_returns_404_when_patient_scoped_meal_not_found():
    db = database_returning(None)

    with pytest.raises(HTTPException) as exc_info:
        await start_patient_meal(
            patient_id=uuid4(),
            meal_id=uuid4(),
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Meal not found"

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_endpoint_rejects_second_start_of_same_meal():
    patient_id = uuid4()

    value = meal(
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    db = database_returning(value, None)

    with pytest.raises(HTTPException) as exc_info:
        await start_patient_meal(
            patient_id=patient_id,
            meal_id=value.id,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "cannot be started" in exc_info.value.detail

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_endpoint_rejects_second_active_meal_for_same_patient():
    patient_id = uuid4()

    captured = meal(
        patient_id=patient_id,
        status="captured",
    )
    active = meal(
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 15),
    )

    db = database_returning(
        captured,
        active.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await start_patient_meal(
            patient_id=patient_id,
            meal_id=captured.id,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Patient already has an active meal"

    assert captured.status == "captured"
    assert captured.started_at is None

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_another_patient_may_start_their_own_meal():
    patient_b = uuid4()
    value = meal(patient_id=patient_b)

    # The active-meal lookup is patient-scoped, so another patient's active
    # meal is not returned by this query.
    db = database_returning(value, None)

    result = await start_patient_meal(
        patient_id=patient_b,
        meal_id=value.id,
        db=db,
    )

    assert result.status == "active"
    assert result.started_at is not None

    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_active_meal_returns_patient_active_meal():
    patient_id = uuid4()
    active = meal(
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    db = database_returning(active)

    result = await get_active_patient_meal(
        patient_id=patient_id,
        db=db,
    )

    assert result is active
    assert result.patient_id == patient_id
    assert result.status == "active"


@pytest.mark.asyncio
async def test_get_active_meal_returns_404_when_none_exists():
    db = database_returning(None)

    with pytest.raises(HTTPException) as exc_info:
        await get_active_patient_meal(
            patient_id=uuid4(),
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No active meal found"


@pytest.mark.asyncio
async def test_consumption_rejected_before_meal_is_started():
    from decimal import Decimal
    from unittest.mock import patch

    from app.api.meals import update_meal_consumption
    from app.models import MealCarbGroup
    from app.schema.schemas import MealConsumptionUpdate

    patient_id = uuid4()
    value = meal(
        patient_id=patient_id,
        status="captured",
    )

    group = MealCarbGroup(
        id=uuid4(),
        meal_id=value.id,
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )
    value.carb_groups = [group]

    db = database_returning(value)

    payload = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 2,
                "consumed_quantity_grams": 20,
            }
        ]
    )

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            new=AsyncMock(return_value=[]),
        ) as build_timeline,
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            new=AsyncMock(),
        ) as stage_timeline,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await update_meal_consumption(
                patient_id=patient_id,
                meal_id=value.id,
                consumption_update=payload,
                db=db,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Actual consumption can only be recorded for an active meal"
    )

    assert group.consumed_quantity_grams is None
    assert group.consumed_carbs_grams is None

    build_timeline.assert_not_awaited()
    stage_timeline.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumption_allowed_after_meal_is_started():
    from decimal import Decimal
    from unittest.mock import patch

    from app.api.meals import update_meal_consumption
    from app.models import MealCarbGroup
    from app.schema.schemas import MealConsumptionUpdate

    patient_id = uuid4()
    value = meal(
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 35),
    )

    group = MealCarbGroup(
        id=uuid4(),
        meal_id=value.id,
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )
    value.carb_groups = [group]

    db = database_returning(value)

    payload = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 2,
                "consumed_quantity_grams": 20,
            }
        ]
    )

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            new=AsyncMock(),
        ),
        patch(
            "app.api.meals.complete_meal_recording_if_ready",
            new=AsyncMock(return_value=False),
        ) as complete_if_ready,
    ):
        result = await update_meal_consumption(
            patient_id=patient_id,
            meal_id=value.id,
            consumption_update=payload,
            db=db,
        )

    assert result is value
    assert value.status == "active"
    assert value.started_at == datetime(2026, 9, 8, 12, 35)

    assert group.consumed_quantity_grams == Decimal("20")
    assert group.consumed_carbs_grams == Decimal("20.0")

    db.flush.assert_awaited_once()
    complete_if_ready.assert_awaited_once_with(
        db=db,
        patient_id=patient_id,
        meal_id=value.id,
    )
    db.commit.assert_awaited_once()
