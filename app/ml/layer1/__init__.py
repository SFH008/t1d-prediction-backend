"""Phase 3 Layer 1: Data Pipeline.

Components:
  - TrainingDatasetBuilder: Extract + align PostgreSQL data
  - DataValidator: Validate data quality
  - ChronologicalSplitter: Split chronologically (no temporal leakage)
  - CanonicalFeatures: Compute base features for IOB + LSTM trainers
"""

from app.ml.layer1.phase3_types import (
    ValidationResult,
    DataGap,
    SplitInfo,
    FeatureSchema,
    DataQualityMetrics,
)
from app.ml.layer1.training_dataset_builder import TrainingDatasetBuilder
from app.ml.layer1.data_validator import DataValidator
from app.ml.layer1.chronological_splitter import (
    ChronologicalSplitter,
    TimeSeriesCrossValidator,
)
from app.ml.layer1.canonical_features import CanonicalFeatures

__all__ = [
    "ValidationResult",
    "DataGap",
    "SplitInfo",
    "FeatureSchema",
    "DataQualityMetrics",
    "TrainingDatasetBuilder",
    "DataValidator",
    "ChronologicalSplitter",
    "TimeSeriesCrossValidator",
    "CanonicalFeatures",
]