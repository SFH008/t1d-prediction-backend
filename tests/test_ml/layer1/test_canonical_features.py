"""Tests for CanonicalFeatures."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.ml.layer1.canonical_features import CanonicalFeatures


class TestCanonicalFeatures:
    """Test feature computation."""

    def test_compute_glucose_rate_of_change(self):
        """Should compute first derivative of glucose."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100, 105, 110, 115, 120, 125, 130, 135, 140, 145],
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "glucose_rate_of_change" in result.columns
        assert pd.isna(result["glucose_rate_of_change"].iloc[0])
        assert result["glucose_rate_of_change"].iloc[1] == 1.0  # (105-100)/5 = 1.0

    def test_compute_glucose_acceleration(self):
        """Should compute 2nd derivative (acceleration)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100 + 5*i for i in range(20)],  # Linear: 100, 105, 110, ...
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "glucose_acceleration" in result.columns
        # For linear glucose increase, acceleration should be ~0
        assert result["glucose_acceleration"].iloc[2] is not None

    def test_compute_temporal_features(self):
        """Should compute hour, day-of-week, time-of-day."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15 14:30:00", periods=10, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100] * 10,
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "hour_of_day" in result.columns
        assert result["hour_of_day"].iloc[0] == 14
        assert "day_of_week" in result.columns
        assert "time_of_day_minutes" in result.columns
        # January 15, 2024 is a Monday (dayofweek=0)
        assert result["day_of_week"].iloc[0] == 0

    def test_compute_day_periods(self):
        """Should compute is_night, is_morning, is_afternoon, is_evening."""
        # Midnight
        df_night = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01 02:00:00", periods=5, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100] * 5,
        })
        features = CanonicalFeatures()
        result = features.compute(df_night)
        assert result["is_night"].iloc[0] == 1
        assert result["is_morning"].iloc[0] == 0

        # Morning
        df_morning = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01 09:00:00", periods=5, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100] * 5,
        })
        result = features.compute(df_morning)
        assert result["is_morning"].iloc[0] == 1
        assert result["is_night"].iloc[0] == 0

    def test_compute_activity_recency(self):
        """Should compute minutes since last activity."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100] * 20,
            "activity_intensity": [None] * 5 + [50] + [None] * 5 + [75] + [None] * 8,
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "minutes_since_activity" in result.columns
        # At index 5 (first activity), should be 0
        assert result["minutes_since_activity"].iloc[5] == 0.0
        # At index 11 (second activity), should be 0
        assert result["minutes_since_activity"].iloc[11] == 0.0

    def test_compute_cumulative_sums(self):
        """Should compute cumulative insulin and carbs."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100] * 10,
            "insulin_bolus_units": [0, 5, 0, 0, 5, 0, 0, 0, 5, 0],
            "carb_intake_grams": [0, 30, 0, 0, 0, 45, 0, 0, 0, 0],
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "insulin_cumsum" in result.columns
        assert "carbs_cumsum" in result.columns
        # Cumsum should increase with each event
        assert result["insulin_cumsum"].iloc[1] == 5
        assert result["insulin_cumsum"].iloc[4] == 10
        assert result["carbs_cumsum"].iloc[5] == 75

    def test_compute_glucose_history_windows(self):
        """Should compute rolling mean/std over 30, 60, 120 min windows."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=50, freq="5min", tz=timezone.utc),
            "glucose_mg_dl": [100 + i % 20 for i in range(50)],
        })

        features = CanonicalFeatures()
        result = features.compute(df)

        assert "glucose_30min_mean" in result.columns
        assert "glucose_30min_std" in result.columns
        assert "glucose_60min_mean" in result.columns
        assert "glucose_60min_std" in result.columns
        assert "glucose_120min_mean" in result.columns
        assert "glucose_120min_std" in result.columns

    def test_get_iob_features(self):
        """Should return correct IOB feature list."""
        features = CanonicalFeatures.get_iob_features()

        assert isinstance(features, list)
        assert "glucose_mg_dl" in features
        assert "insulin_bolus_units" in features
        assert "carb_intake_grams" in features
        assert "hour_of_day" in features

    def test_get_lstm_features(self):
        """Should return correct LSTM feature list."""
        features = CanonicalFeatures.get_lstm_features()

        assert isinstance(features, list)
        assert "glucose_acceleration" in features
        assert "glucose_30min_mean" in features
        assert "activity_intensity" in features
        assert len(features) > 15

    def test_get_all_features(self):
        """Should return all possible features."""
        features = CanonicalFeatures.get_all_features()

        assert isinstance(features, list)
        assert len(features) > 30
        assert "glucose_mg_dl" in features
        assert "glucose_rate_of_change" in features
        assert "hour_of_day" in features