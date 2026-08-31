"""
Shared types and dataclasses for Phase 3 Layer 1.

These structures are used across dataset builder, validator, splitter, and features.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


@dataclass
class ValidationResult:
    """Result of data validation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def raise_if_invalid(self):
        """Raise ValueError if validation failed."""
        if not self.is_valid:
            error_msg = f"Data validation failed:\n"
            if self.errors:
                error_msg += f"Errors:\n" + "\n".join(f"  - {e}" for e in self.errors)
            if self.warnings:
                error_msg += f"\nWarnings:\n" + "\n".join(f"  - {w}" for w in self.warnings)
            if self.summary:
                error_msg += f"\n\nSummary:\n{self.summary}"
            raise ValueError(error_msg)

    def to_json(self) -> str:
        """Serialize to JSON for logging."""
        return json.dumps({
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'summary': self.summary,
            'metadata': self.metadata,
        }, default=str)

    def __str__(self):
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        return f"{status}\n{self.summary}"


@dataclass
class DataGap:
    """Represents a gap in time-series data (e.g., CGM sensor error)."""

    start_time: datetime
    end_time: datetime
    duration_minutes: float
    gap_reason: Optional[str] = None  # e.g., "sensor_restart", "signal_loss"

    def __str__(self):
        return f"Gap: {self.start_time} → {self.end_time} ({self.duration_minutes:.1f} min)"


@dataclass
class SplitInfo:
    """Information about chronological data split."""

    train_start: datetime
    train_end: datetime
    val_start: datetime
    val_end: datetime
    test_start: datetime
    test_end: datetime

    train_count: int
    val_count: int
    test_count: int

    train_fraction: float
    val_fraction: float
    test_fraction: float

    def __str__(self):
        return (
            f"Split Info:\n"
            f"  Train: {self.train_start} → {self.train_end} ({self.train_count} samples, {self.train_fraction*100:.1f}%)\n"
            f"  Val:   {self.val_start} → {self.val_end} ({self.val_count} samples, {self.val_fraction*100:.1f}%)\n"
            f"  Test:  {self.test_start} → {self.test_end} ({self.test_count} samples, {self.test_fraction*100:.1f}%)"
        )

    def verify_no_overlap(self) -> bool:
        """Verify chronological order (no overlap)."""
        if not (self.train_end < self.val_start):
            raise ValueError(f"Train/Val overlap: train ends {self.train_end}, val starts {self.val_start}")
        if not (self.val_end < self.test_start):
            raise ValueError(f"Val/Test overlap: val ends {self.val_end}, test starts {self.test_start}")
        return True


@dataclass
class FeatureSchema:
    """Schema of features available in dataset."""

    raw_features: List[str] = field(default_factory=list)
    """Columns from TrainingDatasetBuilder (glucose, insulin, carbs, etc.)"""

    computed_features: List[str] = field(default_factory=list)
    """Features computed by CanonicalFeatures (glucose_rate, hour_of_day, etc.)"""

    feature_types: Dict[str, str] = field(default_factory=dict)
    """Map feature_name → dtype (e.g., 'glucose_mg_dl' → 'float32')"""

    nullable_features: List[str] = field(default_factory=list)
    """Features that may contain NaN (sparse events like insulin)"""

    def all_features(self) -> List[str]:
        """Return all available features (raw + computed)."""
        return self.raw_features + self.computed_features

    def iob_features(self) -> List[str]:
        """Features needed by IOB trainer."""
        return [
            'timestamp',
            'glucose_mg_dl',
            'insulin_bolus_units',
            'insulin_basal_units',
            'carb_intake_grams',
            'glucose_rate_of_change',
            'hour_of_day',
            'day_of_week',
            'insulin_total_dose',
            'carb_total_intake',
        ]

    def lstm_features(self) -> List[str]:
        """Features needed by LSTM trainer."""
        return [
            'timestamp',
            'glucose_mg_dl',
            'glucose_rate_of_change',
            'glucose_acceleration',
            'glucose_30min_change',
            'insulin_bolus_units',
            'insulin_basal_units',
            'carb_intake_grams',
            'hour_of_day',
            'day_of_week',
            'time_of_day_minutes',
            'activity_intensity',
            'minutes_since_activity',
        ]


class DataQualityMetrics:
    """Aggregate statistics about dataset quality."""

    def __init__(self):
        self.total_samples: int = 0
        self.missing_glucose_count: int = 0
        self.missing_insulin_count: int = 0
        self.missing_carbs_count: int = 0
        self.glucose_outlier_count: int = 0
        self.insulin_outlier_count: int = 0
        self.duplicate_timestamp_count: int = 0
        self.gaps: List[DataGap] = []

    def missing_glucose_fraction(self) -> float:
        """Fraction of samples missing glucose readings."""
        if self.total_samples == 0:
            return 0.0
        return self.missing_glucose_count / self.total_samples

    def missing_insulin_fraction(self) -> float:
        """Fraction of samples missing insulin events."""
        if self.total_samples == 0:
            return 0.0
        return self.missing_insulin_count / self.total_samples

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_samples': self.total_samples,
            'missing_glucose_count': self.missing_glucose_count,
            'missing_glucose_fraction': self.missing_glucose_fraction(),
            'missing_insulin_count': self.missing_insulin_count,
            'missing_insulin_fraction': self.missing_insulin_fraction(),
            'missing_carbs_count': self.missing_carbs_count,
            'glucose_outlier_count': self.glucose_outlier_count,
            'insulin_outlier_count': self.insulin_outlier_count,
            'duplicate_timestamp_count': self.duplicate_timestamp_count,
            'gap_count': len(self.gaps),
            'total_gap_minutes': sum(g.duration_minutes for g in self.gaps),
        }