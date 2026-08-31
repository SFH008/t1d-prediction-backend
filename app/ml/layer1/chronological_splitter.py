"""
Phase 3c: Chronological Data Splitter

Splits time-series data chronologically (no random splits).

CRITICAL RULE:
Future observations must never influence models evaluated on past observations.

This prevents temporal data leakage where a model "sees the future" during training
and becomes artificially accurate on evaluation data.

Split pattern:
    |---------- TRAIN ----------|--- VALIDATION ---|--- TEST ---|
                                                time →
"""

import logging
from typing import Tuple, List
from datetime import datetime

import pandas as pd
import numpy as np

from app.ml.layer1.phase3_types import SplitInfo


logger = logging.getLogger(__name__)


class ChronologicalSplitter:
    """
    Split time-series data chronologically into train/validation/test sets.

    Ensures:
    - All train data is before validation data
    - All validation data is before test data
    - No overlap between splits
    - Temporal order preserved in each split
    """

    @staticmethod
    def split(
        df: pd.DataFrame,
        train_fraction: float = 0.60,
        val_fraction: float = 0.20,
        test_fraction: float = 0.20,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, SplitInfo]:
        """
        Split dataframe chronologically into train/validation/test.

        Args:
            df: DataFrame with 'timestamp' column, sorted chronologically
            train_fraction: Fraction of data for training (default 0.60)
            val_fraction: Fraction for validation (default 0.20)
            test_fraction: Fraction for testing (default 0.20)

        Returns:
            Tuple of (train_df, val_df, test_df, split_info)

        Raises:
            ValueError: If fractions don't sum to 1.0, df is empty, or missing timestamp
        """
        # Validate inputs
        if not (abs(train_fraction + val_fraction + test_fraction - 1.0) < 1e-6):
            raise ValueError(
                f"Fractions must sum to 1.0, got {train_fraction + val_fraction + test_fraction}"
            )

        if len(df) == 0:
            raise ValueError("Cannot split empty dataframe")

        if 'timestamp' not in df.columns:
            raise ValueError("Dataframe must have 'timestamp' column")

        # Sort by timestamp to ensure chronological order
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Calculate split indices
        n = len(df)
        train_idx = int(n * train_fraction)
        val_idx = train_idx + int(n * val_fraction)

        # Extract splits
        train_df = df.iloc[:train_idx].copy()
        val_df = df.iloc[train_idx:val_idx].copy()
        test_df = df.iloc[val_idx:].copy()

        # Verify no overlap
        ChronologicalSplitter._verify_no_overlap(train_df, val_df, test_df)

        # Build split info
        split_info = SplitInfo(
            train_start=train_df['timestamp'].iloc[0],
            train_end=train_df['timestamp'].iloc[-1],
            val_start=val_df['timestamp'].iloc[0],
            val_end=val_df['timestamp'].iloc[-1],
            test_start=test_df['timestamp'].iloc[0],
            test_end=test_df['timestamp'].iloc[-1],
            train_count=len(train_df),
            val_count=len(val_df),
            test_count=len(test_df),
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
        )

        logger.info(f"Split dataset chronologically:\n{split_info}")

        return train_df, val_df, test_df, split_info

    @staticmethod
    def _verify_no_overlap(
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> bool:
        """
        Verify that splits don't overlap (no temporal leakage).

        Raises:
            AssertionError: If any overlap detected
        """
        if len(train_df) > 0 and len(val_df) > 0:
            if not (train_df['timestamp'].max() < val_df['timestamp'].min()):
                raise AssertionError(
                    f"Train/Val overlap: train ends {train_df['timestamp'].max()}, "
                    f"val starts {val_df['timestamp'].min()}"
                )

        if len(val_df) > 0 and len(test_df) > 0:
            if not (val_df['timestamp'].max() < test_df['timestamp'].min()):
                raise AssertionError(
                    f"Val/Test overlap: val ends {val_df['timestamp'].max()}, "
                    f"test starts {test_df['timestamp'].min()}"
                )

        return True

    @staticmethod
    def split_by_date(
        df: pd.DataFrame,
        train_end_date: datetime,
        val_end_date: datetime,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, SplitInfo]:
        """
        Split by explicit date boundaries (alternative to fractional split).

        Useful when you want to train on specific months/years.

        Args:
            df: DataFrame with 'timestamp' column
            train_end_date: End of training data (exclusive)
            val_end_date: End of validation data (exclusive)

        Returns:
            Tuple of (train_df, val_df, test_df, split_info)

        Example:
            from datetime import datetime
            train_end = datetime(2023, 6, 1, tzinfo=timezone.utc)
            val_end = datetime(2023, 8, 1, tzinfo=timezone.utc)

            train, val, test, info = ChronologicalSplitter.split_by_date(
                df, train_end, val_end
            )
        """
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        train_df = df[df['timestamp'] < train_end_date].copy()
        val_df = df[(df['timestamp'] >= train_end_date) & (df['timestamp'] < val_end_date)].copy()
        test_df = df[df['timestamp'] >= val_end_date].copy()

        if len(train_df) == 0 or len(val_df) == 0 or len(test_df) == 0:
            raise ValueError(
                f"Invalid date split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
            )

        # Calculate fractions for info
        total = len(train_df) + len(val_df) + len(test_df)
        train_frac = len(train_df) / total
        val_frac = len(val_df) / total
        test_frac = len(test_df) / total

        split_info = SplitInfo(
            train_start=train_df['timestamp'].iloc[0],
            train_end=train_df['timestamp'].iloc[-1],
            val_start=val_df['timestamp'].iloc[0],
            val_end=val_df['timestamp'].iloc[-1],
            test_start=test_df['timestamp'].iloc[0],
            test_end=test_df['timestamp'].iloc[-1],
            train_count=len(train_df),
            val_count=len(val_df),
            test_count=len(test_df),
            train_fraction=train_frac,
            val_fraction=val_frac,
            test_fraction=test_frac,
        )

        logger.info(f"Split dataset by date:\n{split_info}")

        return train_df, val_df, test_df, split_info

    @staticmethod
    def verify_no_leakage(
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> bool:
        """
        Verify that splits are chronologically sound (no future in past).

        Returns True if valid, raises AssertionError if leakage detected.

        Example:
            train, val, test, info = splitter.split(df)
            assert splitter.verify_no_leakage(train, val, test)
        """
        try:
            return ChronologicalSplitter._verify_no_overlap(train_df, val_df, test_df)
        except AssertionError as e:
            logger.error(f"Temporal data leakage detected: {e}")
            raise


class TimeSeriesCrossValidator:
    """
    Generate multiple train/val/test splits for cross-validation.

    Unlike random k-fold, this uses a "walk-forward" pattern:
    - Fold 1: Train on [0-30%], validate on [30-50%], test on [50-70%]
    - Fold 2: Train on [0-40%], validate on [40-60%], test on [60-80%]
    - Fold 3: Train on [0-50%], validate on [50-70%], test on [70-90%]

    This prevents any future data leaking into model training.
    """

    @staticmethod
    def generate_folds(
        df: pd.DataFrame,
        num_folds: int = 3,
        test_size: float = 0.20,
        val_size: float = 0.15,
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
        """
        Generate walk-forward time-series folds.

        Args:
            df: Full dataset
            num_folds: Number of CV folds (default 3)
            test_size: Fraction of each fold used for testing (default 0.20)
            val_size: Fraction of each fold used for validation (default 0.15)

        Returns:
            List of (train_df, val_df, test_df) tuples
        """
        df = df.sort_values('timestamp').reset_index(drop=True)
        n = len(df)

        folds = []

        for fold_idx in range(num_folds):
            # Walk-forward: increase training set size
            train_fraction = 0.5 + (fold_idx * 0.1)  # 50%, 60%, 70%
            remaining = 1.0 - train_fraction
            val_fraction = val_size / remaining
            test_fraction = test_size / remaining

            # Calculate indices
            train_idx = int(n * train_fraction)
            val_idx = int(train_idx + n * val_size)

            train_df = df.iloc[:train_idx].copy()
            val_df = df.iloc[train_idx:val_idx].copy()
            test_df = df.iloc[val_idx:].copy()

            if len(train_df) > 0 and len(val_df) > 0 and len(test_df) > 0:
                folds.append((train_df, val_df, test_df))
                logger.info(
                    f"Fold {fold_idx + 1}: "
                    f"train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
                )

        if not folds:
            raise ValueError(f"Could not generate {num_folds} valid folds")

        return folds