"""Integration tests for Phase 3 Layer 1."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.ml.layer1 import (
    TrainingDatasetBuilder,
    DataValidator,
    ChronologicalSplitter,
    CanonicalFeatures,
)


def create_synthetic_dataset(days: int = 7) -> pd.DataFrame:
    """Create synthetic glucose dataset for testing."""
    n_samples = days * 24 * 12  # 5-minute intervals
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    timestamps = [start_time + timedelta(minutes=5*i) for i in range(n_samples)]

    glucose = 120 + np.random.normal(0, 10, n_samples)
    glucose = np.clip(glucose, 50, 300)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "glucose_mg_dl": glucose,
        "glucose_source": "CGM",
        "insulin_bolus_units": np.random.uniform(0, 5, n_samples),
        "insulin_basal_units": 0.5,
        "carb_intake_grams": np.random.uniform(0, 30, n_samples),
        "activity_intensity": np.zeros(n_samples),
    })

    # Make sparse (set some to NaN)
    insulin_mask = np.random.random(n_samples) > 0.95
    df.loc[~insulin_mask, "insulin_bolus_units"] = np.nan

    carb_mask = np.random.random(n_samples) > 0.98
    df.loc[~carb_mask, "carb_intake_grams"] = np.nan

    return df


class TestLayer1Integration:
    """Test full Layer 1 pipeline."""

    def test_full_pipeline_extract_validate_split_features(self):
        """Test: Extract → Validate → Split → Features."""
        # Create synthetic data
        raw_df = create_synthetic_dataset(days=7)

        # Validate
        validator = DataValidator()
        result = validator.validate(raw_df)
        assert result.is_valid, f"Validation failed: {result.summary}"

        # Split
        splitter = ChronologicalSplitter()
        train, val, test, info = splitter.split(raw_df)

        # Verify no overlap
        assert splitter.verify_no_leakage(train, val, test)

        # Compute features
        features = CanonicalFeatures()
        train_X = features.compute(train)
        val_X = features.compute(val)
        test_X = features.compute(test)

        # Verify outputs
        assert len(train_X) > 0
        assert len(val_X) > 0
        assert len(test_X) > 0
        assert "glucose_rate_of_change" in train_X.columns
        assert "hour_of_day" in train_X.columns