from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.absorption_curve import PatientAbsorptionInterval
from app.services.absorption_persistence import replace_current_forecast


def _forecast_timeline(
    *,
    start: datetime,
    count: int = 72,
) -> list[PatientAbsorptionInterval]:
    rows = []

    for index in range(count):
        interval_start = start + timedelta(minutes=index * 5)

        rows.append(
            PatientAbsorptionInterval(
                interval_start=interval_start,
                interval_end=interval_start + timedelta(minutes=5),
                base_absorbed_carbs_grams=Decimal("1.0"),
                hormonal_multiplier=Decimal("1.0"),
                activity_multiplier=Decimal("1.0"),
                adjusted_absorbed_carbs_grams=Decimal("1.0"),
                component_count=1,
            )
        )

    return rows


class _ExecuteResult:
    rowcount = 72


class _ForecastSession:
    def __init__(self, *, fail_commit=False):
        self.fail_commit = fail_commit
        self.execute_calls = []
        self.added_all = []
        self.commit_called = False
        self.rollback_called = False

    async def execute(self, stmt):
        self.execute_calls.append(stmt)
        return _ExecuteResult()

    def add_all(self, items):
        self.added_all.extend(items)

    async def commit(self):
        self.commit_called = True

        if self.fail_commit:
            raise SQLAlchemyError(
                "forced forecast replacement failure"
            )

    async def rollback(self):
        self.rollback_called = True


@pytest.mark.asyncio
async def test_replace_current_forecast_persists_exactly_72_rows():
    patient_id = uuid4()
    anchor = datetime(2026, 9, 3, 12, 37)
    grid_start = datetime(2026, 9, 3, 12, 40)

    timeline = _forecast_timeline(start=grid_start)
    session = _ForecastSession()

    rows = await replace_current_forecast(
        db=session,
        patient_id=patient_id,
        forecast_anchor_timestamp=anchor,
        forecast_grid_start=grid_start,
        timeline=timeline,
    )

    assert len(rows) == 72
    assert len(session.added_all) == 72
    assert session.commit_called is True
    assert session.rollback_called is False


@pytest.mark.asyncio
async def test_replace_current_forecast_snapshots_metadata():
    patient_id = uuid4()
    anchor = datetime(2026, 9, 3, 12, 37)
    grid_start = datetime(2026, 9, 3, 12, 40)

    session = _ForecastSession()

    rows = await replace_current_forecast(
        db=session,
        patient_id=patient_id,
        forecast_anchor_timestamp=anchor,
        forecast_grid_start=grid_start,
        timeline=_forecast_timeline(start=grid_start),
    )

    first = rows[0]
    last = rows[-1]

    assert first.patient_id == patient_id
    assert first.forecast_anchor_timestamp == anchor
    assert first.forecast_grid_start == grid_start
    assert first.interval_start == grid_start
    assert first.interval_end == grid_start + timedelta(minutes=5)

    assert first.deterministic_model_version == (
        "deterministic_linear_v1"
    )

    assert last.interval_start == (
        grid_start + timedelta(minutes=355)
    )
    assert last.interval_end == (
        grid_start + timedelta(minutes=360)
    )


@pytest.mark.asyncio
async def test_replace_current_forecast_rejects_non_72_timeline_before_delete():
    session = _ForecastSession()

    with pytest.raises(
        ValueError,
        match="exactly 72",
    ):
        await replace_current_forecast(
            db=session,
            patient_id=uuid4(),
            forecast_anchor_timestamp=datetime(
                2026, 9, 3, 12, 37
            ),
            forecast_grid_start=datetime(
                2026, 9, 3, 12, 40
            ),
            timeline=_forecast_timeline(
                start=datetime(2026, 9, 3, 12, 40),
                count=71,
            ),
        )

    # Validation must happen before destructive replacement.
    assert session.execute_calls == []
    assert session.added_all == []
    assert session.commit_called is False
    assert session.rollback_called is False


@pytest.mark.asyncio
async def test_replace_current_forecast_rolls_back_on_commit_failure():
    patient_id = uuid4()
    anchor = datetime(2026, 9, 3, 12, 37)
    grid_start = datetime(2026, 9, 3, 12, 40)

    session = _ForecastSession(
        fail_commit=True
    )

    with pytest.raises(SQLAlchemyError):
        await replace_current_forecast(
            db=session,
            patient_id=patient_id,
            forecast_anchor_timestamp=anchor,
            forecast_grid_start=grid_start,
            timeline=_forecast_timeline(
                start=grid_start
            ),
        )

    # DELETE and INSERT belong to the same transaction.
    assert len(session.execute_calls) == 1
    assert len(session.added_all) == 72
    assert session.commit_called is True
    assert session.rollback_called is True

@pytest.mark.asyncio
async def test_replace_current_forecast_rejects_wrong_grid_before_delete():
    patient_id = uuid4()
    anchor = datetime(2026, 9, 3, 12, 37)
    grid_start = datetime(2026, 9, 3, 12, 40)

    timeline = _forecast_timeline(
        start=grid_start
    )

    # Still 72 rows, but no longer the requested forecast grid.
    timeline[0] = PatientAbsorptionInterval(
        interval_start=grid_start + timedelta(minutes=1),
        interval_end=grid_start + timedelta(minutes=6),
        base_absorbed_carbs_grams=Decimal("1.0"),
        hormonal_multiplier=Decimal("1.0"),
        activity_multiplier=Decimal("1.0"),
        adjusted_absorbed_carbs_grams=Decimal("1.0"),
        component_count=1,
    )

    session = _ForecastSession()

    with pytest.raises(
        ValueError,
        match="forecast grid",
    ):
        await replace_current_forecast(
            db=session,
            patient_id=patient_id,
            forecast_anchor_timestamp=anchor,
            forecast_grid_start=grid_start,
            timeline=timeline,
        )

    assert session.execute_calls == []
    assert session.added_all == []
    assert session.commit_called is False