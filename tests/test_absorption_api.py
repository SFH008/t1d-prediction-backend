from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.absorption import get_absorption_timeline


class _ScalarCollection:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ScalarResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarCollection(self._values)


class _AbsorptionApiSession:
    """
    Fake async DB session for the absorption timeline read endpoint.

    execute() sequence:
      1. patient lookup
      2. historical absorption query
      3. current forecast query
    """

    def __init__(
        self,
        *,
        patient,
        history=None,
        forecast=None,
    ):
        self.patient = patient
        self.history = history or []
        self.forecast = forecast or []

        self.execute_count = 0
        self.executed_statements = []

    async def execute(self, stmt):
        self.execute_count += 1
        self.executed_statements.append(stmt)

        if self.execute_count == 1:
            return _ScalarResult(
                value=self.patient
            )

        if self.execute_count == 2:
            return _ScalarResult(
                values=self.history
            )

        if self.execute_count == 3:
            return _ScalarResult(
                values=self.forecast
            )

        raise AssertionError(
            f"Unexpected execute call #{self.execute_count}"
        )


def _history_point(
    *,
    patient_id,
    interval_start,
    version="deterministic_linear_v1",
    mode="original",
):
    return SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        interval_start=interval_start,
        interval_end=(
            interval_start + timedelta(minutes=5)
        ),
        base_absorbed_carbs_grams=Decimal("1.000000"),
        hormonal_multiplier=Decimal("1.00000"),
        activity_multiplier=Decimal("1.00000"),
        adjusted_absorbed_carbs_grams=Decimal("1.000000"),
        component_count=1,
        derivation_model="deterministic_linear",
        derivation_version=version,
        derivation_mode=mode,
        derived_at=datetime(
            2026, 9, 3, 12, 0
        ),
    )


def _forecast_point(
    *,
    patient_id,
    interval_start,
    anchor_timestamp,
    grid_start,
):
    return SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        forecast_anchor_timestamp=anchor_timestamp,
        forecast_grid_start=grid_start,
        interval_start=interval_start,
        interval_end=(
            interval_start + timedelta(minutes=5)
        ),
        base_absorbed_carbs_grams=Decimal("2.000000"),
        hormonal_multiplier=Decimal("1.00000"),
        activity_multiplier=Decimal("1.00000"),
        adjusted_absorbed_carbs_grams=Decimal("2.000000"),
        component_count=2,
        deterministic_model_version=(
            "deterministic_linear_v1"
        ),
        ml_model_version=None,
        ml_predicted_absorbed_carbs_grams=None,
        ml_lower_bound_grams=None,
        ml_upper_bound_grams=None,
        ml_confidence=None,
        forecast_generated_at=datetime(
            2026, 9, 3, 12, 37
        ),
    )


@pytest.mark.asyncio
async def test_get_absorption_timeline_returns_404_for_missing_patient():
    patient_id = uuid4()

    session = _AbsorptionApiSession(
        patient=None,
    )

    with pytest.raises(HTTPException) as exc:
        await get_absorption_timeline(
            patient_id=patient_id,
            db=session,
        )

    assert exc.value.status_code == 404
    assert str(patient_id) in exc.value.detail

    # No timeline queries should run when patient does not exist.
    assert session.execute_count == 1


@pytest.mark.asyncio
async def test_get_absorption_timeline_returns_history_and_forecast():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    history_start = datetime(
        2026, 9, 3, 6, 40
    )

    forecast_start = datetime(
        2026, 9, 3, 12, 40
    )

    anchor = datetime(
        2026, 9, 3, 12, 37
    )

    history_descending = [
        _history_point(
            patient_id=patient_id,
            interval_start=(
                history_start
                + timedelta(minutes=index * 5)
            ),
        )
        for index in reversed(range(72))
    ]

    forecast = [
        _forecast_point(
            patient_id=patient_id,
            interval_start=(
                forecast_start
                + timedelta(minutes=index * 5)
            ),
            anchor_timestamp=anchor,
            grid_start=forecast_start,
        )
        for index in range(72)
    ]

    session = _AbsorptionApiSession(
        patient=patient,
        history=history_descending,
        forecast=forecast,
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    assert result.patient_id == patient_id

    assert len(result.history) == 72
    assert len(result.forecast) == 72

    assert result.history[0].interval_start == history_start

    assert result.history[-1].interval_start == (
        history_start
        + timedelta(minutes=355)
    )

    assert result.forecast[0].interval_start == (
        forecast_start
    )

    assert result.forecast[-1].interval_start == (
        forecast_start
        + timedelta(minutes=355)
    )


@pytest.mark.asyncio
async def test_get_absorption_timeline_history_is_returned_ascending():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    start = datetime(
        2026, 9, 3, 6, 40
    )

    # The API query asks PostgreSQL for newest-first history,
    # then reverses the result for frontend display.
    history_descending = [
        _history_point(
            patient_id=patient_id,
            interval_start=start + timedelta(minutes=10),
        ),
        _history_point(
            patient_id=patient_id,
            interval_start=start + timedelta(minutes=5),
        ),
        _history_point(
            patient_id=patient_id,
            interval_start=start,
        ),
    ]

    session = _AbsorptionApiSession(
        patient=patient,
        history=history_descending,
        forecast=[],
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    assert [
        point.interval_start
        for point in result.history
    ] == [
        start,
        start + timedelta(minutes=5),
        start + timedelta(minutes=10),
    ]


@pytest.mark.asyncio
async def test_get_absorption_timeline_forecast_is_returned_ascending():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    anchor = datetime(
        2026, 9, 3, 12, 37
    )

    grid_start = datetime(
        2026, 9, 3, 12, 40
    )

    forecast = [
        _forecast_point(
            patient_id=patient_id,
            interval_start=grid_start,
            anchor_timestamp=anchor,
            grid_start=grid_start,
        ),
        _forecast_point(
            patient_id=patient_id,
            interval_start=(
                grid_start + timedelta(minutes=5)
            ),
            anchor_timestamp=anchor,
            grid_start=grid_start,
        ),
        _forecast_point(
            patient_id=patient_id,
            interval_start=(
                grid_start + timedelta(minutes=10)
            ),
            anchor_timestamp=anchor,
            grid_start=grid_start,
        ),
    ]

    session = _AbsorptionApiSession(
        patient=patient,
        history=[],
        forecast=forecast,
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    assert [
        point.interval_start
        for point in result.forecast
    ] == [
        grid_start,
        grid_start + timedelta(minutes=5),
        grid_start + timedelta(minutes=10),
    ]


@pytest.mark.asyncio
async def test_get_absorption_timeline_exposes_history_provenance():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    point = _history_point(
        patient_id=patient_id,
        interval_start=datetime(
            2026, 9, 3, 6, 40
        ),
        version="deterministic_linear_v1",
        mode="original",
    )

    session = _AbsorptionApiSession(
        patient=patient,
        history=[point],
        forecast=[],
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    history = result.history[0]

    assert history.derivation_model == (
        "deterministic_linear"
    )
    assert history.derivation_version == (
        "deterministic_linear_v1"
    )
    assert history.derivation_mode == "original"

    assert history.hormonal_multiplier == 1.0
    assert history.activity_multiplier == 1.0


@pytest.mark.asyncio
async def test_get_absorption_timeline_exposes_forecast_metadata():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    anchor = datetime(
        2026, 9, 3, 12, 37
    )

    grid_start = datetime(
        2026, 9, 3, 12, 40
    )

    point = _forecast_point(
        patient_id=patient_id,
        interval_start=grid_start,
        anchor_timestamp=anchor,
        grid_start=grid_start,
    )

    session = _AbsorptionApiSession(
        patient=patient,
        history=[],
        forecast=[point],
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    forecast = result.forecast[0]

    assert forecast.forecast_anchor_timestamp == anchor
    assert forecast.forecast_grid_start == grid_start

    assert forecast.deterministic_model_version == (
        "deterministic_linear_v1"
    )

    assert forecast.ml_model_version is None
    assert forecast.ml_predicted_absorbed_carbs_grams is None
    assert forecast.ml_lower_bound_grams is None
    assert forecast.ml_upper_bound_grams is None
    assert forecast.ml_confidence is None


@pytest.mark.asyncio
async def test_get_absorption_timeline_does_not_write_or_rebuild():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    session = _AbsorptionApiSession(
        patient=patient,
        history=[],
        forecast=[],
    )

    result = await get_absorption_timeline(
        patient_id=patient_id,
        db=session,
    )

    assert result.patient_id == patient_id
    assert result.history == []
    assert result.forecast == []

    # Read API should perform only:
    #   patient SELECT
    #   history SELECT
    #   forecast SELECT
    assert session.execute_count == 3

    # The fake intentionally implements no add(), flush(),
    # commit(), or rollback(). If the endpoint attempted to write,
    # this test would fail with AttributeError.