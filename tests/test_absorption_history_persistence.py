from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.absorption_curve import PatientAbsorptionInterval
from app.services.absorption_persistence import persist_absorption_history
from app.models import (
    PatientAbsorptionForecast,
    PatientAbsorptionHistory,
)


def _history_timeline(
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


class _HistorySession:
    def __init__(self, *, fail_commit=False):
        self.fail_commit = fail_commit
        self.added_all = []
        self.commit_called = False
        self.rollback_called = False

    def add_all(self, items):
        self.added_all.extend(items)

    async def commit(self):
        self.commit_called = True

        if self.fail_commit:
            raise SQLAlchemyError(
                "forced history persistence failure"
            )

    async def rollback(self):
        self.rollback_called = True


@pytest.mark.asyncio
async def test_persist_absorption_history_creates_expected_rows():
    patient_id = uuid4()
    history_start = datetime(2026, 9, 3, 6, 40)

    session = _HistorySession()

    rows = await persist_absorption_history(
        db=session,
        patient_id=patient_id,
        timeline=_history_timeline(
            start=history_start
        ),
        derivation_model="deterministic_linear",
        derivation_version="deterministic_linear_v1",
        derivation_mode="original",
    )

    assert len(rows) == 72
    assert len(session.added_all) == 72
    assert session.commit_called is True
    assert session.rollback_called is False


@pytest.mark.asyncio
async def test_persist_absorption_history_snapshots_derivation_metadata():
    patient_id = uuid4()
    history_start = datetime(2026, 9, 3, 6, 40)

    session = _HistorySession()

    rows = await persist_absorption_history(
        db=session,
        patient_id=patient_id,
        timeline=_history_timeline(
            start=history_start
        ),
        derivation_model="deterministic_linear",
        derivation_version="deterministic_linear_v1",
        derivation_mode="original",
    )

    first = rows[0]

    assert first.patient_id == patient_id
    assert first.interval_start == history_start
    assert first.interval_end == (
        history_start + timedelta(minutes=5)
    )

    assert first.base_absorbed_carbs_grams == Decimal("1.0")
    assert first.adjusted_absorbed_carbs_grams == Decimal("1.0")

    assert first.hormonal_multiplier == Decimal("1.0")
    assert first.activity_multiplier == Decimal("1.0")
    assert first.component_count == 1

    assert first.derivation_model == "deterministic_linear"
    assert first.derivation_version == "deterministic_linear_v1"
    assert first.derivation_mode == "original"


@pytest.mark.asyncio
async def test_persist_absorption_history_accepts_retrospective_version():
    session = _HistorySession()

    rows = await persist_absorption_history(
        db=session,
        patient_id=uuid4(),
        timeline=_history_timeline(
            start=datetime(2026, 9, 3, 6, 40)
        ),
        derivation_model="deterministic_linear",
        derivation_version="deterministic_linear_v2",
        derivation_mode="retrospective",
    )

    assert all(
        row.derivation_version == "deterministic_linear_v2"
        for row in rows
    )

    assert all(
        row.derivation_mode == "retrospective"
        for row in rows
    )


@pytest.mark.asyncio
async def test_persist_absorption_history_rejects_invalid_mode_before_write():
    session = _HistorySession()

    with pytest.raises(
        ValueError,
        match="derivation_mode",
    ):
        await persist_absorption_history(
            db=session,
            patient_id=uuid4(),
            timeline=_history_timeline(
                start=datetime(2026, 9, 3, 6, 40)
            ),
            derivation_model="deterministic_linear",
            derivation_version="deterministic_linear_v1",
            derivation_mode="invalid",
        )

    assert session.added_all == []
    assert session.commit_called is False
    assert session.rollback_called is False


@pytest.mark.asyncio
async def test_persist_absorption_history_rejects_invalid_grid_before_write():
    timeline = _history_timeline(
        start=datetime(2026, 9, 3, 6, 40)
    )

    timeline[0] = PatientAbsorptionInterval(
        interval_start=datetime(2026, 9, 3, 6, 41),
        interval_end=datetime(2026, 9, 3, 6, 46),
        base_absorbed_carbs_grams=Decimal("1.0"),
        hormonal_multiplier=Decimal("1.0"),
        activity_multiplier=Decimal("1.0"),
        adjusted_absorbed_carbs_grams=Decimal("1.0"),
        component_count=1,
    )

    session = _HistorySession()

    with pytest.raises(
        ValueError,
        match="history grid",
    ):
        await persist_absorption_history(
            db=session,
            patient_id=uuid4(),
            timeline=timeline,
            derivation_model="deterministic_linear",
            derivation_version="deterministic_linear_v1",
            derivation_mode="original",
        )

    assert session.added_all == []
    assert session.commit_called is False


@pytest.mark.asyncio
async def test_persist_absorption_history_rolls_back_on_commit_failure():
    session = _HistorySession(
        fail_commit=True
    )

    with pytest.raises(SQLAlchemyError):
        await persist_absorption_history(
            db=session,
            patient_id=uuid4(),
            timeline=_history_timeline(
                start=datetime(2026, 9, 3, 6, 40)
            ),
            derivation_model="deterministic_linear",
            derivation_version="deterministic_linear_v1",
            derivation_mode="original",
        )

    assert len(session.added_all) == 72
    assert session.commit_called is True
    assert session.rollback_called is True