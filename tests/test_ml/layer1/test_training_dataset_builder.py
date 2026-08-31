"""
Phase 3a: Training Dataset Builder

Extracts patient data from PostgreSQL and aligns records chronologically.

Handles:
- Multi-table joins (glucose, insulin, carbs, activity, hormonal contexts)
- 5-minute resampling
- Gap detection (CGM sensor issues)
- Timezone handling (UTC-aware)
- Null/missing value handling
"""

from datetime import datetime, timedelta
from typing import Tuple, List, Optional
import logging

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import DictCursor

from app.ml.layer1.phase3_types import DataGap, DataQualityMetrics, ValidationResult


logger = logging.getLogger(__name__)


class TrainingDatasetBuilder:
    """
    Extract raw training data from PostgreSQL and prepare for model training.

    The dataset contains:
    - Glucose readings (CGM or fingerstick meter)
    - Insulin events (bolus and basal)
    - Carbohydrate intakes
    - Activity events
    - Hormonal contexts
    - Therapy limits

    All data is aligned to a common 5-minute timeline.
    """

    # Constants
    RESAMPLE_INTERVAL = '5T'  # 5-minute intervals
    MAX_GAP_MINUTES = 30  # Gaps > 30 min considered sensor error

    def __init__(self, db_connection_string: str):
        """
        Initialize dataset builder with database connection.

        Args:
            db_connection_string: psycopg2 connection string
                e.g., "postgresql://user:pass@localhost:5432/glucose_db"
        """
        self.db_connection_string = db_connection_string
        self.conn = None
        self._connect()

    def _connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(self.db_connection_string)
            logger.info("Connected to PostgreSQL database")
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def extract_patient_data(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Extract all relevant data for a patient over a time range.

        Args:
            patient_id: UUID of patient
            start_date: Start of time range (inclusive, UTC)
            end_date: End of time range (inclusive, UTC)

        Returns:
            DataFrame with columns:
            - timestamp (sorted, 5-min intervals, UTC-aware)
            - glucose_mg_dl (forward-filled)
            - glucose_source (CGM or Meter)
            - insulin_bolus_units (sparse, event-based)
            - insulin_basal_units (forward-filled)
            - carb_intake_grams (sparse, event-based)
            - activity_intensity (sparse)
            - activity_duration_min (sparse)
            - hormone_type (sparse)
            - hormone_context (sparse)
            - therapy_limit_type (sparse)

        Raises:
            psycopg2.Error: If query fails
            ValueError: If patient_id not found
        """
        logger.info(
            f"Extracting data for patient {patient_id} "
            f"from {start_date} to {end_date}"
        )

        # Verify patient exists
        if not self._patient_exists(patient_id):
            raise ValueError(f"Patient {patient_id} not found")

        # Extract each table
        glucose_df = self._extract_glucose(patient_id, start_date, end_date)
        insulin_df = self._extract_insulin(patient_id, start_date, end_date)
        carbs_df = self._extract_carbs(patient_id, start_date, end_date)
        activity_df = self._extract_activity(patient_id, start_date, end_date)
        hormonal_df = self._extract_hormonal(patient_id, start_date, end_date)
        therapy_df = self._extract_therapy_limits(patient_id, start_date, end_date)

        # Merge on timestamp
        df = self._merge_datasets(
            glucose_df, insulin_df, carbs_df, activity_df, hormonal_df, therapy_df
        )

        # Resample to 5-minute intervals
        df = self._resample_to_5min(df)

        # Forward-fill scalar values (keep event columns sparse)
        df = self._forward_fill_scalars(df)

        logger.info(f"Extracted {len(df)} records for patient {patient_id}")

        return df

    def _patient_exists(self, patient_id: str) -> bool:
        """Check if patient exists in database."""
        query = "SELECT 1 FROM patients WHERE patient_id = %s"
        with self.conn.cursor() as cur:
            cur.execute(query, (patient_id,))
            return cur.fetchone() is not None

    def _extract_glucose(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract glucose readings."""
        query = """
        SELECT
            timestamp,
            glucose_mg_dl,
            source
        FROM glucose_readings
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        # Rename for clarity
        df = df.rename(columns={'source': 'glucose_source'})

        logger.info(f"  Extracted {len(df)} glucose readings")
        return df

    def _extract_insulin(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract insulin events (bolus and basal)."""
        query = """
        SELECT
            timestamp,
            CASE
                WHEN type = 'BOLUS' THEN units
                ELSE NULL
            END AS insulin_bolus_units,
            CASE
                WHEN type = 'BASAL' THEN units
                ELSE NULL
            END AS insulin_basal_units
        FROM insulin_events
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        logger.info(f"  Extracted {len(df)} insulin events")
        return df

    def _extract_carbs(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract carbohydrate intake events."""
        query = """
        SELECT
            timestamp,
            carbs_grams
        FROM carb_intakes
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        df = df.rename(columns={'carbs_grams': 'carb_intake_grams'})

        logger.info(f"  Extracted {len(df)} carb intake events")
        return df

    def _extract_activity(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract activity events."""
        query = """
        SELECT
            timestamp,
            intensity,
            duration_minutes
        FROM activities
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        df = df.rename(columns={
            'intensity': 'activity_intensity',
            'duration_minutes': 'activity_duration_min',
        })

        logger.info(f"  Extracted {len(df)} activity events")
        return df

    def _extract_hormonal(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract hormonal context (period, stress, illness, etc.)."""
        query = """
        SELECT
            timestamp,
            hormone_type,
            context
        FROM hormonal_contexts
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        df = df.rename(columns={
            'hormone_type': 'hormone_type',
            'context': 'hormone_context',
        })

        logger.info(f"  Extracted {len(df)} hormonal context records")
        return df

    def _extract_therapy_limits(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract therapy limits (ISF, ICR, targets, etc.)."""
        query = """
        SELECT
            timestamp,
            limit_type
        FROM therapy_limits
        WHERE patient_id = %s
            AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(patient_id, start_date, end_date),
            parse_dates=['timestamp'],
        )

        df = df.rename(columns={'limit_type': 'therapy_limit_type'})

        logger.info(f"  Extracted {len(df)} therapy limit records")
        return df

    @staticmethod
    def _merge_datasets(
        glucose_df: pd.DataFrame,
        insulin_df: pd.DataFrame,
        carbs_df: pd.DataFrame,
        activity_df: pd.DataFrame,
        hormonal_df: pd.DataFrame,
        therapy_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Merge all extracted dataframes on timestamp.

        Uses outer merge to preserve all timestamps from all tables.
        """
        # Start with glucose (typically the most frequent)
        df = glucose_df.copy()

        # Merge in order (outer join on timestamp)
        for other_df, name in [
            (insulin_df, 'insulin'),
            (carbs_df, 'carbs'),
            (activity_df, 'activity'),
            (hormonal_df, 'hormonal'),
            (therapy_df, 'therapy'),
        ]:
            if len(other_df) > 0:
                df = pd.merge(df, other_df, on='timestamp', how='outer')

            logger.debug(f"  Merged {name}: {len(df)} total records")

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    @staticmethod
    def _resample_to_5min(df: pd.DataFrame) -> pd.DataFrame:
        """
        Resample data to 5-minute intervals.

        - Sets timestamp as index
        - Resamples to 5T (5-minute) frequency
        - Uses 'first' aggregation (first non-null value in each interval)
        - Resets index to make timestamp a column again
        """
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df.set_index('timestamp', inplace=True)

        # Resample: use 'first' to get first non-null value in each 5-min window
        df = df.resample('5T').first()

        df.reset_index(inplace=True)

        return df

    @staticmethod
    def _forward_fill_scalars(df: pd.DataFrame) -> pd.DataFrame:
        """
        Forward-fill scalar values (e.g., glucose, basal insulin).

        Sparse event columns (bolus, carbs, activity) are left as-is (not forward-filled).

        Scalars that carry over from previous readings:
        - glucose_mg_dl (scalar measurement)
        - glucose_source (scalar measurement)
        - insulin_basal_units (scalar rate)

        Events that should NOT be forward-filled:
        - insulin_bolus_units (event: only occurs at time of injection)
        - carb_intake_grams (event: only at time of meal)
        - activity_* (event: only at start of activity)
        - hormone_* (event: context-dependent)
        - therapy_limit_type (event: when changed)
        """
        df = df.copy()

        scalar_columns = [
            'glucose_mg_dl',
            'glucose_source',
            'insulin_basal_units',
        ]

        for col in scalar_columns:
            if col in df.columns:
                df[col] = df[col].fillna(method='ffill')

        return df

    def detect_gaps(
        self,
        df: pd.DataFrame,
        max_gap_minutes: int = MAX_GAP_MINUTES,
    ) -> List[DataGap]:
        """
        Detect gaps in CGM data (e.g., sensor restart, signal loss).

        A gap is a period where glucose readings are missing for > max_gap_minutes.

        Args:
            df: DataFrame from extract_patient_data()
            max_gap_minutes: Threshold for gap detection (default 30 min)

        Returns:
            List of DataGap objects with start, end, and duration
        """
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        # Find where glucose is present
        has_glucose = df['glucose_mg_dl'].notna()

        gaps = []
        gap_start = None

        for i, (idx, row) in enumerate(df.iterrows()):
            if not has_glucose.iloc[i]:  # No glucose
                if gap_start is None:
                    gap_start = i
            else:  # Has glucose
                if gap_start is not None:
                    gap_start_time = df.iloc[gap_start]['timestamp']
                    gap_end_time = row['timestamp']
                    duration_minutes = (gap_end_time - gap_start_time).total_seconds() / 60

                    if duration_minutes > max_gap_minutes:
                        gaps.append(DataGap(
                            start_time=gap_start_time,
                            end_time=gap_end_time,
                            duration_minutes=duration_minutes,
                            gap_reason='unknown',
                        ))

                    gap_start = None

        # Handle gap at end of dataset
        if gap_start is not None:
            gap_start_time = df.iloc[gap_start]['timestamp']
            gap_end_time = df.iloc[-1]['timestamp']
            duration_minutes = (gap_end_time - gap_start_time).total_seconds() / 60

            if duration_minutes > max_gap_minutes:
                gaps.append(DataGap(
                    start_time=gap_start_time,
                    end_time=gap_end_time,
                    duration_minutes=duration_minutes,
                    gap_reason='end_of_data',
                ))

        logger.info(f"Detected {len(gaps)} gaps > {max_gap_minutes} minutes")
        for gap in gaps:
            logger.debug(f"  {gap}")

        return gaps

    def compute_quality_metrics(self, df: pd.DataFrame) -> DataQualityMetrics:
        """
        Compute data quality metrics for the dataset.

        Args:
            df: DataFrame from extract_patient_data()

        Returns:
            DataQualityMetrics with counts and fractions
        """
        metrics = DataQualityMetrics()
        metrics.total_samples = len(df)

        # Count missing values
        metrics.missing_glucose_count = df['glucose_mg_dl'].isna().sum()
        metrics.missing_insulin_count = df['insulin_bolus_units'].isna().sum()
        metrics.missing_carbs_count = df['carb_intake_grams'].isna().sum()

        # Count outliers (outside hard constraints)
        if 'glucose_mg_dl' in df.columns:
            metrics.glucose_outlier_count = (
                ((df['glucose_mg_dl'] < 40) | (df['glucose_mg_dl'] > 400))
                .sum()
            )

        if 'insulin_bolus_units' in df.columns:
            metrics.insulin_outlier_count = (
                ((df['insulin_bolus_units'] < 0) | (df['insulin_bolus_units'] > 100))
                .sum()
            )

        # Count duplicates
        metrics.duplicate_timestamp_count = df['timestamp'].duplicated().sum()

        # Detect gaps
        metrics.gaps = self.detect_gaps(df)

        logger.info(f"Quality metrics: {metrics.to_dict()}")

        return metrics