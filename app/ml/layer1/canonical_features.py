"""
Phase 3d: Canonical Feature Engineering

Computes foundational features from raw dataset.

Output: DataFrame with raw columns + computed features that both IOB and LSTM trainers can use.

Each trainer selects the features it needs:
- IOB trainer: glucose, insulin, carbs, temporal features, IOB/COB (computed by trainer)
- LSTM trainer: glucose derivatives, temporal, activity, sequences

Philosophy:
- One canonical pipeline computes all features once
- Trainers SELECT the features they need
- No feature computation inside model-specific trainers
"""

import logging
from typing import List, Optional

import pandas as pd
import numpy as np


logger = logging.getLogger(__name__)


class CanonicalFeatures:
    """
    Compute canonical features from raw dataset.

    Input: DataFrame from TrainingDatasetBuilder
    Output: Same DataFrame with additional feature columns

    Features computed:
    1. Glucose derivatives (rate of change, acceleration)
    2. Temporal features (hour, day of week, time in minutes)
    3. Activity recency (minutes since last activity)
    4. Cumulative sums (insulin, carbs)
    5. Recent history (glucose change over periods)
    """

    # Default indices for glucose history windows
    GLUCOSE_HISTORY_WINDOWS = [6, 12, 24]  # 5-min * N = 30-min, 60-min, 120-min windows

    def __init__(self):
        """Initialize feature engineer."""
        self.logger = logging.getLogger(__name__)

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all canonical features.

        Args:
            df: DataFrame with 'timestamp' column and measurement columns

        Returns:
            Same DataFrame with additional feature columns added
        """
        df = df.copy()

        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        # 1. Glucose features
        if 'glucose_mg_dl' in df.columns:
            df = self._compute_glucose_features(df)

        # 2. Temporal features
        if 'timestamp' in df.columns:
            df = self._compute_temporal_features(df)

        # 3. Activity recency
        if 'activity_intensity' in df.columns:
            df['minutes_since_activity'] = self._compute_minutes_since_event(
                df, 'activity_intensity'
            )

        # 4. Cumulative sums (for IOB/COB baseline)
        if 'insulin_bolus_units' in df.columns:
            df['insulin_cumsum'] = df['insulin_bolus_units'].fillna(0).cumsum()

        if 'carb_intake_grams' in df.columns:
            df['carbs_cumsum'] = df['carb_intake_grams'].fillna(0).cumsum()

        # 5. Recent glucose history
        if 'glucose_mg_dl' in df.columns:
            df = self._compute_glucose_history(df)

        self.logger.info(f"Computed {len(df.columns)} feature columns")

        return df

    @staticmethod
    def _compute_glucose_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute glucose-derived features.

        Features:
        - glucose_rate_of_change: mg/dL per minute (1st derivative)
        - glucose_acceleration: rate of change of rate (2nd derivative)
        - glucose_30min_change: total change over 30 minutes
        """
        # Rate of change (per minute, since intervals are 5 min)
        df['glucose_rate_of_change'] = df['glucose_mg_dl'].diff() / 5.0

        # Acceleration (2nd derivative)
        df['glucose_acceleration'] = df['glucose_rate_of_change'].diff()

        # Change over 30 minutes (6 × 5-min intervals)
        df['glucose_30min_change'] = df['glucose_mg_dl'].diff(periods=6)

        # Change over 60 minutes (12 × 5-min intervals)
        df['glucose_60min_change'] = df['glucose_mg_dl'].diff(periods=12)

        # Change over 120 minutes (24 × 5-min intervals)
        df['glucose_120min_change'] = df['glucose_mg_dl'].diff(periods=24)

        # Velocity category (fast rise, slow rise, flat, slow fall, fast fall)
        df['glucose_velocity_category'] = pd.cut(
            df['glucose_rate_of_change'],
            bins=[-np.inf, -2, -0.5, 0.5, 2, np.inf],
            labels=['fast_fall', 'slow_fall', 'flat', 'slow_rise', 'fast_rise'],
        )

        return df

    @staticmethod
    def _compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute temporal features from timestamp.

        Features:
        - hour_of_day: 0-23
        - day_of_week: 0-6 (Monday=0, Sunday=6)
        - time_of_day_minutes: 0-1439 (minutes since midnight)
        - is_night: 1 if 22:00-06:00, else 0
        - is_morning: 1 if 06:00-12:00, else 0
        - is_afternoon: 1 if 12:00-18:00, else 0
        - is_evening: 1 if 18:00-22:00, else 0
        """
        df['hour_of_day'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['day_of_month'] = df['timestamp'].dt.day
        df['month'] = df['timestamp'].dt.month

        # Time in minutes since midnight
        df['time_of_day_minutes'] = df['timestamp'].dt.hour * 60 + df['timestamp'].dt.minute

        # Time periods (important for diabetes patterns)
        hour = df['timestamp'].dt.hour
        df['is_night'] = ((hour >= 22) | (hour < 6)).astype(int)
        df['is_morning'] = ((hour >= 6) & (hour < 12)).astype(int)
        df['is_afternoon'] = ((hour >= 12) & (hour < 18)).astype(int)
        df['is_evening'] = ((hour >= 18) & (hour < 22)).astype(int)

        # Day type (weekday vs weekend)
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

        return df

    @staticmethod
    def _compute_minutes_since_event(df: pd.DataFrame, event_col: str) -> pd.Series:
        """
        Helper: calculate minutes since last non-null event in a column.

        For example, _compute_minutes_since_event(df, 'activity_intensity')
        gives minutes since last activity.

        Returns NaN if no previous event.
        """
        result = []
        last_event_idx = None

        for i in range(len(df)):
            if pd.notna(df[event_col].iloc[i]):
                # Event occurred at this index
                last_event_idx = i
                result.append(0.0)
            elif last_event_idx is not None:
                # Time since last event (in 5-min intervals, convert to minutes)
                intervals = i - last_event_idx
                result.append(intervals * 5.0)
            else:
                # No prior event
                result.append(np.nan)

        return pd.Series(result, index=df.index)

    @staticmethod
    def _compute_glucose_history(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute rolling statistics on glucose (recent history).

        Features:
        - glucose_30min_mean: mean glucose over last 30 min
        - glucose_30min_std: std dev of glucose over last 30 min
        - glucose_60min_mean, glucose_60min_std
        - glucose_120min_mean, glucose_120min_std
        """
        # 30-minute windows (6 × 5-min intervals)
        df['glucose_30min_mean'] = df['glucose_mg_dl'].rolling(window=6, min_periods=1).mean()
        df['glucose_30min_std'] = df['glucose_mg_dl'].rolling(window=6, min_periods=1).std()

        # 60-minute windows (12 × 5-min intervals)
        df['glucose_60min_mean'] = df['glucose_mg_dl'].rolling(window=12, min_periods=1).mean()
        df['glucose_60min_std'] = df['glucose_mg_dl'].rolling(window=12, min_periods=1).std()

        # 120-minute windows (24 × 5-min intervals)
        df['glucose_120min_mean'] = df['glucose_mg_dl'].rolling(window=24, min_periods=1).mean()
        df['glucose_120min_std'] = df['glucose_mg_dl'].rolling(window=24, min_periods=1).std()

        return df

    @staticmethod
    def get_iob_features() -> List[str]:
        """
        Return list of feature names used by IOB trainer.

        These are the columns IOB trainer will SELECT from the full feature set.
        """
        return [
            'timestamp',
            'glucose_mg_dl',
            'glucose_rate_of_change',
            'insulin_bolus_units',
            'insulin_basal_units',
            'carb_intake_grams',
            'hour_of_day',
            'day_of_week',
            'is_night',
            'is_morning',
            'is_afternoon',
            'is_evening',
            'insulin_cumsum',
            'carbs_cumsum',
        ]

    @staticmethod
    def get_lstm_features() -> List[str]:
        """
        Return list of feature names used by LSTM trainer.

        These are the columns LSTM trainer will SELECT from the full feature set.
        Includes temporal, glucose derivatives, and activity.
        """
        return [
            'timestamp',
            'glucose_mg_dl',
            'glucose_rate_of_change',
            'glucose_acceleration',
            'glucose_30min_change',
            'glucose_60min_change',
            'glucose_120min_change',
            'glucose_velocity_category',
            'glucose_30min_mean',
            'glucose_30min_std',
            'glucose_60min_mean',
            'glucose_60min_std',
            'insulin_bolus_units',
            'insulin_basal_units',
            'carb_intake_grams',
            'hour_of_day',
            'day_of_week',
            'day_of_month',
            'month',
            'time_of_day_minutes',
            'is_night',
            'is_morning',
            'is_afternoon',
            'is_evening',
            'is_weekend',
            'activity_intensity',
            'minutes_since_activity',
        ]

    @staticmethod
    def get_all_features() -> List[str]:
        """Return all possible feature names (raw + computed)."""
        raw = [
            'timestamp',
            'glucose_mg_dl',
            'glucose_source',
            'insulin_bolus_units',
            'insulin_basal_units',
            'carb_intake_grams',
            'activity_intensity',
            'activity_duration_min',
            'hormone_type',
            'hormone_context',
            'therapy_limit_type',
        ]

        computed = [
            'glucose_rate_of_change',
            'glucose_acceleration',
            'glucose_30min_change',
            'glucose_60min_change',
            'glucose_120min_change',
            'glucose_velocity_category',
            'glucose_30min_mean',
            'glucose_30min_std',
            'glucose_60min_mean',
            'glucose_60min_std',
            'glucose_120min_mean',
            'glucose_120min_std',
            'hour_of_day',
            'day_of_week',
            'day_of_month',
            'month',
            'time_of_day_minutes',
            'is_night',
            'is_morning',
            'is_afternoon',
            'is_evening',
            'is_weekend',
            'minutes_since_activity',
            'insulin_cumsum',
            'carbs_cumsum',
        ]

        return raw + computed


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function: compute all canonical features in one call.

    Args:
        df: DataFrame from TrainingDatasetBuilder

    Returns:
        DataFrame with all features computed
    """
    engineer = CanonicalFeatures()
    return engineer.compute(df)