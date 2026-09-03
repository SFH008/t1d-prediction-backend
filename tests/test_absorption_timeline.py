from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.absorption_timeline import build_component_curves

from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.exc import SQLAlchemyError

def _component(
    *,
    patient_id,
    meal_timestamp,
    carbs_grams,
    delay_minutes,
    duration_minutes,
):
    meal = SimpleNamespace(
        meal_timestamp=meal_timestamp,
    )

    meal_group = SimpleNamespace(
        carbs_grams=Decimal(str(carbs_grams)),
        meal=meal,
    )

    absorption = SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        meal_carb_group=meal_group,
        absorption_delay_minutes=delay_minutes,
        absorption_duration_minutes=duration_minutes,
        curve_type="linear",
        model_version="deterministic_linear_v1",
    )

    return absorption


def test_build_component_curves_uses_snapshotted_component_values():
    patient_id = uuid4()

    component = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    curves = build_component_curves(
        components=[component],
    )

    assert len(curves) == 1

    curve = curves[0]

    assert curve[0].interval_start == datetime(
        2026, 9, 3, 12, 10
    )

    assert curve[-1].interval_end == datetime(
        2026, 9, 3, 13, 10
    )

    total = sum(
        point.absorbed_carbs_grams
        for point in curve
    )

    assert total == Decimal("30")


def test_build_component_curves_supports_multiple_components():
    patient_id = uuid4()

    components = [
        _component(
            patient_id=patient_id,
            meal_timestamp=datetime(2026, 9, 3, 12, 0),
            carbs_grams=30,
            delay_minutes=10,
            duration_minutes=60,
        ),
        _component(
            patient_id=patient_id,
            meal_timestamp=datetime(2026, 9, 3, 12, 0),
            carbs_grams=60,
            delay_minutes=10,
            duration_minutes=300,
        ),
    ]

    curves = build_component_curves(
        components=components,
    )

    assert len(curves) == 2

    totals = [
        sum(
            point.absorbed_carbs_grams
            for point in curve
        )
        for curve in curves
    ]

    assert totals == [
        Decimal("30"),
        Decimal("60"),
    ]


def test_build_component_curves_rejects_unsupported_curve_type():
    patient_id = uuid4()

    component = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    component.curve_type = "unsupported"

    with pytest.raises(
        ValueError,
        match="curve_type",
    ):
        build_component_curves(
            components=[component],
        )

from app.services.absorption_timeline import (
    build_component_curves,
    component_overlaps_window,
)


def test_component_overlaps_window_when_meal_started_before_window():
    component = _component(
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 3, 5, 0),
        carbs_grams=60,
        delay_minutes=10,
        duration_minutes=300,
    )

    # Absorption: 05:10 -> 10:10
    # Requested window: 06:40 -> 12:40
    assert component_overlaps_window(
        component=component,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    ) is True


def test_component_excluded_when_absorption_ended_at_window_start():
    component = _component(
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 3, 5, 30),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    # Absorption: 05:40 -> 06:40
    assert component_overlaps_window(
        component=component,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    ) is False


def test_component_excluded_when_absorption_starts_at_window_end():
    component = _component(
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 3, 12, 30),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    # Absorption starts exactly at 12:40.
    assert component_overlaps_window(
        component=component,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    ) is False


def test_component_overlaps_when_absorption_crosses_window_start():
    component = _component(
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 3, 6, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    # Absorption: 06:10 -> 07:10
    assert component_overlaps_window(
        component=component,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    ) is True


def test_component_overlaps_when_entirely_inside_window():
    component = _component(
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 3, 9, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    assert component_overlaps_window(
        component=component,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    ) is True

class _ScalarCollection:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _ExecuteResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _ScalarCollection(self.values)


class _TimelineSession:
    def __init__(self, components):
        self.components = components
        self.execute_called = False
        self.executed_stmt = None

    async def execute(self, stmt):
        self.execute_called = True
        self.executed_stmt = stmt
        return _ExecuteResult(self.components)


@pytest.mark.asyncio
async def test_load_overlapping_components_filters_exact_overlap():
    from app.services.absorption_timeline import (
        load_overlapping_components,
    )

    patient_id = uuid4()

    overlapping_old_meal = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 5, 0),
        carbs_grams=60,
        delay_minutes=10,
        duration_minutes=300,
    )

    expired = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 4, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    inside = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 9, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    session = _TimelineSession(
        [
            overlapping_old_meal,
            expired,
            inside,
        ]
    )

    result = await load_overlapping_components(
        db=session,
        patient_id=patient_id,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    )

    assert session.execute_called is True
    assert result == [
        overlapping_old_meal,
        inside,
    ]


@pytest.mark.asyncio
async def test_load_overlapping_components_rejects_invalid_window():
    from app.services.absorption_timeline import (
        load_overlapping_components,
    )

    session = _TimelineSession([])

    with pytest.raises(
        ValueError,
        match="window_end must be after window_start",
    ):
        await load_overlapping_components(
            db=session,
            patient_id=uuid4(),
            window_start=datetime(2026, 9, 3, 12, 0),
            window_end=datetime(2026, 9, 3, 12, 0),
        )

    assert session.execute_called is False

@pytest.mark.asyncio
async def test_load_overlapping_components_query_is_patient_scoped():
    from app.services.absorption_timeline import (
        load_overlapping_components,
    )

    patient_id = uuid4()

    session = _TimelineSession([])

    await load_overlapping_components(
        db=session,
        patient_id=patient_id,
        window_start=datetime(2026, 9, 3, 6, 40),
        window_end=datetime(2026, 9, 3, 12, 40),
    )

    compiled = session.executed_stmt.compile(
        compile_kwargs={"literal_binds": True}
    )

    sql = str(compiled)

    assert "meal_component_absorptions.patient_id" in sql
    assert "meal_component_absorptions.patient_id =" in sql
    assert "meals.meal_timestamp <" in sql
    assert "JOIN meal_carb_groups" in sql
    assert "JOIN meals" in sql

    assert "meals.meal_timestamp" in sql
    assert "2026-09-03 12:40:00" in sql

    assert "JOIN meal_carb_groups" in sql
    assert "JOIN meals" in sql

@pytest.mark.asyncio
async def test_build_patient_absorption_timeline_returns_72_plus_72():
    from app.services.absorption_timeline import (
        build_patient_absorption_timeline,
    )

    patient_id = uuid4()

    component = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    session = _TimelineSession([component])

    result = await build_patient_absorption_timeline(
        db=session,
        patient_id=patient_id,
        anchor_timestamp=datetime(2026, 9, 3, 12, 37),
    )

    assert len(result.history) == 72
    assert len(result.forecast) == 72

    assert result.history_start == datetime(
        2026, 9, 3, 6, 40
    )
    assert result.history_end == datetime(
        2026, 9, 3, 12, 40
    )

    assert result.forecast_start == datetime(
        2026, 9, 3, 12, 40
    )
    assert result.forecast_end == datetime(
        2026, 9, 3, 18, 40
    )


@pytest.mark.asyncio
async def test_build_patient_absorption_timeline_keeps_previous_active_meal():
    from app.services.absorption_timeline import (
        build_patient_absorption_timeline,
    )

    patient_id = uuid4()

    previous = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 10, 0),
        carbs_grams=60,
        delay_minutes=10,
        duration_minutes=300,
    )

    new = _component(
        patient_id=patient_id,
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        carbs_grams=30,
        delay_minutes=10,
        duration_minutes=60,
    )

    session = _TimelineSession([
        previous,
        new,
    ])

    result = await build_patient_absorption_timeline(
        db=session,
        patient_id=patient_id,
        anchor_timestamp=datetime(2026, 9, 3, 12, 37),
    )

    # Both meals are active at forecast start 12:40.
    assert result.forecast[0].component_count == 2


@pytest.mark.asyncio
async def test_build_patient_absorption_timeline_history_and_forecast_are_contiguous():
    from app.services.absorption_timeline import (
        build_patient_absorption_timeline,
    )

    result = await build_patient_absorption_timeline(
        db=_TimelineSession([]),
        patient_id=uuid4(),
        anchor_timestamp=datetime(2026, 9, 3, 12, 37),
    )

    assert result.history_end == result.forecast_start

@pytest.mark.asyncio
async def test_persist_patient_absorption_timeline_commits_once():
    from app.services.absorption_timeline import (
        persist_patient_absorption_timeline,
    )

    patient_id = uuid4()
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    timeline = SimpleNamespace(
        anchor_timestamp=datetime(2026, 9, 3, 12, 37),
        forecast_start=datetime(2026, 9, 3, 12, 40),
        history=[],
        forecast=[],
    )

    history_rows = [SimpleNamespace()]
    forecast_rows = [SimpleNamespace()]

    with (
        patch(
            "app.services.absorption_timeline.stage_absorption_history",
            Mock(return_value=history_rows),
        ) as stage_history,
        patch(
            "app.services.absorption_timeline.stage_current_forecast",
            AsyncMock(return_value=forecast_rows),
        ) as stage_forecast,
    ):
        result = await persist_patient_absorption_timeline(
            db=db,
            patient_id=patient_id,
            timeline=timeline,
        )

    stage_history.assert_called_once()
    stage_forecast.assert_awaited_once()

    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()

    assert result.history_rows is history_rows
    assert result.forecast_rows is forecast_rows


@pytest.mark.asyncio
async def test_persist_patient_absorption_timeline_rolls_back_together():
    from app.services.absorption_timeline import (
        persist_patient_absorption_timeline,
    )

    patient_id = uuid4()

    db = SimpleNamespace(
        commit=AsyncMock(
            side_effect=SQLAlchemyError("commit failed")
        ),
        rollback=AsyncMock(),
    )

    timeline = SimpleNamespace(
        anchor_timestamp=datetime(2026, 9, 3, 12, 37),
        forecast_start=datetime(2026, 9, 3, 12, 40),
        history=[],
        forecast=[],
    )

    with (
        patch(
            "app.services.absorption_timeline.stage_absorption_history",
            Mock(return_value=[]),
        ),
        patch(
            "app.services.absorption_timeline.stage_current_forecast",
            AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(SQLAlchemyError):
            await persist_patient_absorption_timeline(
                db=db,
                patient_id=patient_id,
                timeline=timeline,
            )

    db.commit.assert_awaited_once()
    db.rollback.assert_awaited_once()

