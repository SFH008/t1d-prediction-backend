"""
Tests for the Phase 3a TrainingDatasetBuilder.

These tests target the production implementation in:
    app.ml.layer1.training_dataset_builder
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.ml.layer1.phase3_types import DataGap, DataQualityMetrics
from app.ml.layer1.training_dataset_builder import TrainingDatasetBuilder


@pytest.fixture
def builder():
    """Create a builder without opening a real database connection."""
    instance = object.__new__(TrainingDatasetBuilder)
    instance.db_connection_string = "postgresql+asyncpg://test:test@localhost/test"
    instance.engine = None
    instance._owns_engine = False
    return instance


def test_init_rejects_empty_connection_string():
    with pytest.raises(ValueError, match="cannot be empty"):
        TrainingDatasetBuilder("")


def test_merge_datasets_preserves_all_timestamps():
    glucose = pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-01 00:00:00+00:00"],
            utc=True,
        ),
        "glucose_mg_dl": [120],
        "glucose_source": ["CGM"],
    })

    insulin = pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-01 00:05:00+00:00"],
            utc=True,
        ),
        "insulin_bolus_units": [2.0],
        "insulin_basal_units": [None],
    })

    empty = pd.DataFrame()

    result = TrainingDatasetBuilder._merge_datasets(
        glucose,
        insulin,
        empty,
        empty,
        empty,
        empty,
    )

    assert len(result) == 2
    assert list(result["timestamp"]) == list(
        pd.to_datetime(
            [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:05:00+00:00",
            ],
            utc=True,
        )
    )


def test_merge_datasets_keeps_therapy_limits_as_metadata():
    glucose = pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-01 00:00:00+00:00"],
            utc=True,
        ),
        "glucose_mg_dl": [120],
        "glucose_source": ["CGM"],
    })

    therapy = pd.DataFrame({
        "therapy_limit_type": ["glucose_target"],
        "therapy_lower_bound": [80],
        "therapy_upper_bound": [120],
    })

    result = TrainingDatasetBuilder._merge_datasets(
        glucose,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        therapy,
    )

    assert "therapy_limit_type" not in result.columns
    assert result.attrs["therapy_limits"] == [
        {
            "therapy_limit_type": "glucose_target",
            "therapy_lower_bound": 80,
            "therapy_upper_bound": 120,
        }
    ]


def test_merge_datasets_has_empty_therapy_metadata_when_no_limits():
    glucose = pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-01 00:00:00+00:00"],
            utc=True,
        ),
        "glucose_mg_dl": [120],
    })

    result = TrainingDatasetBuilder._merge_datasets(
        glucose,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )

    assert result.attrs["therapy_limits"] == []


def test_resample_sums_events_within_five_minutes():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:01:00+00:00",
                "2026-01-01 00:04:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, 105],
        "insulin_bolus_units": [1.0, 2.0],
        "insulin_basal_units": [0.1, 0.2],
        "carb_intake_grams": [10.0, 20.0],
    })

    result = TrainingDatasetBuilder._resample_to_5min(df)

    assert len(result) == 1
    assert result.loc[0, "insulin_bolus_units"] == pytest.approx(3.0)
    assert result.loc[0, "insulin_basal_units"] == pytest.approx(0.3)
    assert result.loc[0, "carb_intake_grams"] == pytest.approx(30.0)
    assert result.loc[0, "glucose_mg_dl"] == 100


def test_resample_preserves_first_scalar_value():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:01:00+00:00",
                "2026-01-01 00:04:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, 105],
        "glucose_source": ["CGM", "Meter"],
    })

    result = TrainingDatasetBuilder._resample_to_5min(df)

    assert result.loc[0, "glucose_mg_dl"] == 100
    assert result.loc[0, "glucose_source"] == "CGM"


def test_forward_fill_scalars_only():
    df = pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-01-01",
            periods=3,
            freq="5min",
            tz="UTC",
        ),
        "glucose_mg_dl": [100, None, None],
        "glucose_source": ["CGM", None, None],
        "insulin_basal_units": [0.5, None, None],
        "insulin_bolus_units": [1.0, None, None],
        "carb_intake_grams": [20.0, None, None],
    })

    result = TrainingDatasetBuilder._forward_fill_scalars(df)

    assert result["glucose_mg_dl"].tolist() == [100, 100, 100]
    assert result["glucose_source"].tolist() == ["CGM", "CGM", "CGM"]
    assert result["insulin_basal_units"].tolist() == [0.5, 0.5, 0.5]

    assert pd.isna(result.loc[1, "insulin_bolus_units"])
    assert pd.isna(result.loc[2, "insulin_bolus_units"])
    assert pd.isna(result.loc[1, "carb_intake_grams"])
    assert pd.isna(result.loc[2, "carb_intake_grams"])


def test_detect_gaps_finds_gap_over_threshold(builder):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:05:00+00:00",
                "2026-01-01 00:40:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, None, 110],
    })

    gaps = builder.detect_gaps(df)

    assert len(gaps) == 1
    assert isinstance(gaps[0], DataGap)
    assert gaps[0].duration_minutes == pytest.approx(35.0)
    assert gaps[0].gap_reason == "unknown"


def test_detect_gaps_ignores_gap_at_or_below_threshold(builder):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:35:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, 110],
    })

    gaps = builder.detect_gaps(df)

    assert gaps == []


def test_detect_gaps_handles_end_of_data(builder):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:05:00+00:00",
                "2026-01-01 00:40:00+00:00",
                "2026-01-01 01:15:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, 110, None, None],
    })

    gaps = builder.detect_gaps(df)

    assert len(gaps) == 1
    assert gaps[0].gap_reason == "end_of_data"
    assert gaps[0].duration_minutes == pytest.approx(35.0)


def test_detect_gaps_empty_dataframe(builder):
    gaps = builder.detect_gaps(pd.DataFrame())

    assert gaps == []


def test_detect_gaps_without_glucose_column(builder):
    df = pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-01-01",
            periods=3,
            freq="5min",
            tz="UTC",
        )
    })

    assert builder.detect_gaps(df) == []


def test_compute_quality_metrics(builder):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:05:00+00:00",
                "2026-01-01 00:10:00+00:00",
            ],
            utc=True,
        ),
        "glucose_mg_dl": [100, None, 450],
        "insulin_bolus_units": [1.0, None, 101.0],
        "carb_intake_grams": [20.0, None, 30.0],
    })

    metrics = builder.compute_quality_metrics(df)

    assert isinstance(metrics, DataQualityMetrics)
    assert metrics.total_samples == 3
    assert metrics.missing_glucose_count == 1
    assert metrics.missing_insulin_count == 1
    assert metrics.missing_carbs_count == 1
    assert metrics.glucose_outlier_count == 1
    assert metrics.insulin_outlier_count == 1
    assert metrics.duplicate_timestamp_count == 0


def test_compute_quality_metrics_counts_duplicate_timestamps(builder):
    timestamp = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")

    df = pd.DataFrame({
        "timestamp": [timestamp, timestamp],
        "glucose_mg_dl": [100, 110],
        "insulin_bolus_units": [None, None],
        "carb_intake_grams": [None, None],
    })

    metrics = builder.compute_quality_metrics(df)

    assert metrics.total_samples == 2
    assert metrics.duplicate_timestamp_count == 1


def test_compute_quality_metrics_empty(builder):
    metrics = builder.compute_quality_metrics(pd.DataFrame())

    assert metrics.total_samples == 0
    assert metrics.missing_glucose_count == 0
    assert metrics.gaps == []


@pytest.mark.asyncio
async def test_patient_exists_uses_external_patient_id(builder):
    builder._fetch_all = AsyncMock(return_value=[{"?column?": 1}])

    result = await builder._patient_exists("patient-123")

    assert result is True
    builder._fetch_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_patient_exists_returns_false_when_missing(builder):
    builder._fetch_all = AsyncMock(return_value=[])

    result = await builder._patient_exists("missing")

    assert result is False


@pytest.mark.asyncio
async def test_resolve_patient_db_id(builder):
    builder._fetch_all = AsyncMock(
        return_value=[{"id": "11111111-1111-1111-1111-111111111111"}]
    )

    result = await builder._resolve_patient_db_id("external-123")

    assert result == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_resolve_patient_db_id_raises_for_missing_patient(builder):
    builder._fetch_all = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="external_patient_id='missing'"):
        await builder._resolve_patient_db_id("missing")


@pytest.mark.asyncio
async def test_extract_therapy_limits_uses_configuration_without_timestamp(
    builder,
):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "limit_type": "glucose_target",
                "lower_bound": 80,
                "upper_bound": 120,
                "is_hard_limit": True,
                "time_of_day_start": None,
                "time_of_day_end": None,
                "day_of_week": None,
            }
        ]
    )

    result = await builder._extract_therapy_limits("internal-id")

    assert list(result.columns) == [
        "therapy_limit_type",
        "therapy_lower_bound",
        "therapy_upper_bound",
    ]

    assert result.iloc[0]["therapy_limit_type"] == "glucose_target"
    assert result.iloc[0]["therapy_lower_bound"] == 80
    assert result.iloc[0]["therapy_upper_bound"] == 120

    builder._fetch_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_therapy_limits_returns_empty_schema(builder):
    builder._fetch_all = AsyncMock(return_value=[])

    result = await builder._extract_therapy_limits("internal-id")

    assert result.empty
    assert list(result.columns) == [
        "therapy_limit_type",
        "therapy_lower_bound",
        "therapy_upper_bound",
    ]


@pytest.mark.asyncio
async def test_extract_glucose_maps_database_columns(builder):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "timestamp": datetime(
                    2026,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                "glucose_mg_dl": 120,
                "glucose_source": "CGM",
            }
        ]
    )

    result = await builder._extract_glucose(
        "internal-id",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert list(result.columns) == [
        "timestamp",
        "glucose_mg_dl",
        "glucose_source",
    ]
    assert result.iloc[0]["glucose_mg_dl"] == 120
    assert result.iloc[0]["glucose_source"] == "CGM"


@pytest.mark.asyncio
async def test_extract_insulin_maps_database_columns(builder):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "timestamp": datetime(
                    2026,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                "insulin_bolus_units": 2.5,
                "insulin_basal_units": None,
                "basal_rate": 0.5,
            }
        ]
    )

    result = await builder._extract_insulin(
        "internal-id",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert list(result.columns) == [
        "timestamp",
        "insulin_bolus_units",
        "insulin_basal_units",
    ]
    assert result.iloc[0]["insulin_bolus_units"] == 2.5
    assert result.iloc[0]["insulin_basal_units"] == 0.5


@pytest.mark.asyncio
async def test_extract_hormonal_maps_actual_database_columns(builder):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "timestamp": datetime(
                    2026,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                "hormone_type": "stress",
                "hormone_context": "high",
            }
        ]
    )

    result = await builder._extract_hormonal(
        "internal-id",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert result.iloc[0]["hormone_type"] == "stress"
    assert result.iloc[0]["hormone_context"] == "high"


@pytest.mark.asyncio
async def test_extract_carbs_maps_database_columns(builder):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "timestamp": datetime(
                    2026,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                "carb_intake_grams": 45,
            }
        ]
    )

    result = await builder._extract_carbs(
        "internal-id",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert result.iloc[0]["carb_intake_grams"] == 45


@pytest.mark.asyncio
async def test_extract_activity_maps_database_columns(builder):
    builder._fetch_all = AsyncMock(
        return_value=[
            {
                "timestamp": datetime(
                    2026,
                    1,
                    1,
                    tzinfo=timezone.utc,
                ),
                "activity_intensity": "moderate",
                "activity_duration_min": 30,
            }
        ]
    )

    result = await builder._extract_activity(
        "internal-id",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert result.iloc[0]["activity_intensity"] == "moderate"
    assert result.iloc[0]["activity_duration_min"] == 30
