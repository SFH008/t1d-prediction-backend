"""Tests for ChronologicalSplitter."""

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from app.ml.layer1.chronological_splitter import (
    ChronologicalSplitter,
    TimeSeriesCrossValidator,
)


class TestChronologicalSplitter:
    """Test chronological splitting (no temporal leakage)."""

    def test_split_no_overlap(self):
        """Should verify no overlap between splits."""
        # Create sample data
        dates = pd.date_range("2024-01-01", periods=1000, freq="5min", tz=timezone.utc)
        df = pd.DataFrame({"timestamp": dates, "value": range(1000)})

        splitter = ChronologicalSplitter()
        train, val, test, info = splitter.split(df)

        # Verify no overlap
        assert train["timestamp"].max() < val["timestamp"].min()
        assert val["timestamp"].max() < test["timestamp"].min()

    # Add more tests here

    def test_split_by_date(self):
        """Should split by explicit date boundaries."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=1000, freq="5min", tz=timezone.utc),
            "value": range(1000),
        })

        splitter = ChronologicalSplitter()
        train, val, test, info = splitter.split_by_date(
            df,
            train_end_date=pd.Timestamp("2024-01-02", tz=timezone.utc),
            val_end_date=pd.Timestamp("2024-01-03", tz=timezone.utc),
        )

        assert len(train) > 0
        assert len(val) > 0
        assert len(test) > 0

    def test_walk_forward_cv(self):
        """Should generate walk-forward folds."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=500, freq="5min", tz=timezone.utc),
            "value": range(500),
        })

        folds = TimeSeriesCrossValidator.generate_folds(df, num_folds=3)

        assert len(folds) == 3
        for train, val, test in folds:
            assert len(train) > 0
            assert len(val) > 0
            assert len(test) > 0