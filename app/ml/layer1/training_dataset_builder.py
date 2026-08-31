"""
Phase 3a: Training Dataset Builder

Extracts patient data from PostgreSQL using the application's asyncpg
database stack and aligns records chronologically.

Patient identity:
- patients.external_patient_id is the application/external patient ID.
- patients.id is the internal UUID.
- Child tables store that internal UUID in their patient_id column.

Handles:
- Multi-table extraction (glucose, insulin, carbs, activity, hormonal contexts)
- 5-minute resampling
- Gap detection (CGM sensor issues)
- Timezone handling (UTC-aware)
- Null/missing value handling
- Active therapy-limit configuration

The database URL is expected to be the application's SQLAlchemy async URL:

    postgresql+asyncpg://user:password@host:5432/database

This class uses SQLAlchemy's async engine with asyncpg.
"""

from datetime import datetime
from typing import List, Optional

import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.ml.layer1.phase3_types import (
    DataGap,
    DataQualityMetrics,
)


logger = logging.getLogger(__name__)


class TrainingDatasetBuilder:
    """
    Extract raw training data from PostgreSQL and prepare it for model
    training.

    The dataset contains:
    - Glucose readings
    - Insulin events
    - Carbohydrate intake events
    - Activity events
    - Hormonal/context events
    - Active therapy limits

    All time-series data is aligned to a common 5-minute timeline.

    The public extraction API is asynchronous because the application
    database uses asyncpg.
    """

    RESAMPLE_INTERVAL = "5min"
    MAX_GAP_MINUTES = 30

    def __init__(
        self,
        db_connection_string: str,
        engine: Optional[AsyncEngine] = None,
    ):
        """
        Initialize the dataset builder.

        Args:
            db_connection_string:
                SQLAlchemy async database URL, for example:

                postgresql+asyncpg://t1d_app:password@localhost:5432/t1d_glucose

            engine:
                Optional existing AsyncEngine. If supplied, ownership of
                the engine remains with the caller.
        """
        if not db_connection_string:
            raise ValueError("Database connection string cannot be empty")

        self.db_connection_string = db_connection_string
        self._owns_engine = engine is None

        self.engine = engine or create_async_engine(
            db_connection_string,
            pool_pre_ping=True,
        )

    async def close(self) -> None:
        """Dispose the database engine if this builder owns it."""
        if self._owns_engine and self.engine is not None:
            await self.engine.dispose()
            logger.info("PostgreSQL database engine disposed")

    async def _fetch_all(
        self,
        query: str,
        params: dict,
    ) -> List[dict]:
        """Execute an async SQL query and return rows as dictionaries."""
        async with self.engine.connect() as conn:
            result = await conn.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]

    async def _patient_exists(
        self,
        patient_id: str,
    ) -> bool:
        """
        Check whether the external/application patient ID exists.

        Important:
            patient_id supplied by the caller maps to
            patients.external_patient_id, not patients.id.
        """
        query = """
            SELECT 1
            FROM patients
            WHERE external_patient_id = :patient_id
            LIMIT 1
        """

        rows = await self._fetch_all(
            query,
            {"patient_id": patient_id},
        )

        return bool(rows)

    async def _resolve_patient_db_id(
        self,
        patient_id: str,
    ) -> str:
        """
        Resolve external_patient_id to the internal patients.id UUID.
        """
        query = """
            SELECT id
            FROM patients
            WHERE external_patient_id = :patient_id
            LIMIT 1
        """

        rows = await self._fetch_all(
            query,
            {"patient_id": patient_id},
        )

        if not rows:
            raise ValueError(
                f"Patient with external_patient_id={patient_id!r} not found"
            )

        return str(rows[0]["id"])

    async def extract_patient_data(
        self,
        patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Extract all relevant data for an external patient ID.

        Args:
            patient_id:
                Application/external patient ID stored in
                patients.external_patient_id.

            start_date:
                Start of requested time range, UTC.

            end_date:
                End of requested time range, UTC.

        Returns:
            DataFrame with canonical Layer 1 columns.
        """
        logger.info(
            "Extracting data for external patient %s from %s to %s",
            patient_id,
            start_date,
            end_date,
        )

        internal_patient_id = await self._resolve_patient_db_id(patient_id)

        logger.info(
            "Resolved external patient %s to internal patients.id %s",
            patient_id,
            internal_patient_id,
        )

        glucose_df = await self._extract_glucose(
            internal_patient_id,
            start_date,
            end_date,
        )

        insulin_df = await self._extract_insulin(
            internal_patient_id,
            start_date,
            end_date,
        )

        carbs_df = await self._extract_carbs(
            internal_patient_id,
            start_date,
            end_date,
        )

        activity_df = await self._extract_activity(
            internal_patient_id,
            start_date,
            end_date,
        )

        hormonal_df = await self._extract_hormonal(
            internal_patient_id,
            start_date,
            end_date,
        )

        therapy_df = await self._extract_therapy_limits(
            internal_patient_id,
        )

        df = self._merge_datasets(
            glucose_df,
            insulin_df,
            carbs_df,
            activity_df,
            hormonal_df,
            therapy_df,
        )

        if df.empty:
            logger.warning(
                "No physiological records found for patient %s "
                "in the requested time range",
                patient_id,
            )
            return self._empty_dataset()

        df = self._resample_to_5min(df)
        df = self._forward_fill_scalars(df)

        logger.info(
            "Extracted %d aligned records for patient %s",
            len(df),
            patient_id,
        )

        return df

    async def _extract_glucose(
        self,
        internal_patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Extract glucose readings.

        Actual database columns:
            glucose_value_mg_dl
            reading_type
            source
        """
        query = """
            SELECT
                timestamp,
                glucose_value_mg_dl AS glucose_mg_dl,
                source AS glucose_source
            FROM glucose_readings
            WHERE patient_id = :patient_id
              AND timestamp BETWEEN :start_date AND :end_date
              AND is_valid = TRUE
            ORDER BY timestamp ASC
        """

        rows = await self._fetch_all(
            query,
            {
                "patient_id": internal_patient_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "glucose_mg_dl",
                "glucose_source",
            ],
        )

        logger.info("  Extracted %d glucose readings", len(df))

        return df

    async def _extract_insulin(
        self,
        internal_patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Extract insulin events.

        Actual database columns:
            insulin_type
            dose_units
            basal_rate
        """
        query = """
            SELECT
                timestamp,

                CASE
                    WHEN LOWER(insulin_type) IN ('bolus', 'rapid')
                    THEN dose_units
                    ELSE NULL
                END AS insulin_bolus_units,

                CASE
                    WHEN LOWER(insulin_type) = 'basal'
                    THEN dose_units
                    ELSE NULL
                END AS insulin_basal_units,

                basal_rate
            FROM insulin_events
            WHERE patient_id = :patient_id
              AND timestamp BETWEEN :start_date AND :end_date
            ORDER BY timestamp ASC
        """

        rows = await self._fetch_all(
            query,
            {
                "patient_id": internal_patient_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "insulin_bolus_units",
                "insulin_basal_units",
                "basal_rate",
            ],
        )

        # Prefer the recorded basal rate when available. Otherwise retain
        # the delivered basal dose as the canonical basal quantity.
        if "basal_rate" in df.columns:
            df["insulin_basal_units"] = df[
                "insulin_basal_units"
            ].combine_first(df["basal_rate"])

            df = df.drop(columns=["basal_rate"])

        logger.info("  Extracted %d insulin events", len(df))

        return df

    async def _extract_carbs(
        self,
        internal_patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract carbohydrate intake events."""
        query = """
            SELECT
                timestamp,
                carbs_grams AS carb_intake_grams
            FROM carb_intakes
            WHERE patient_id = :patient_id
              AND timestamp BETWEEN :start_date AND :end_date
            ORDER BY timestamp ASC
        """

        rows = await self._fetch_all(
            query,
            {
                "patient_id": internal_patient_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "carb_intake_grams",
            ],
        )

        logger.info("  Extracted %d carbohydrate events", len(df))

        return df

    async def _extract_activity(
        self,
        internal_patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Extract activity events."""
        query = """
            SELECT
                timestamp,
                intensity AS activity_intensity,
                duration_minutes AS activity_duration_min
            FROM activities
            WHERE patient_id = :patient_id
              AND timestamp BETWEEN :start_date AND :end_date
            ORDER BY timestamp ASC
        """

        rows = await self._fetch_all(
            query,
            {
                "patient_id": internal_patient_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "activity_intensity",
                "activity_duration_min",
            ],
        )

        logger.info("  Extracted %d activity events", len(df))

        return df

    async def _extract_hormonal(
        self,
        internal_patient_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Extract hormonal/context records.

        Actual database columns:
            context_type
            context_value
        """
        query = """
            SELECT
                timestamp,
                context_type AS hormone_type,
                context_value AS hormone_context
            FROM hormonal_contexts
            WHERE patient_id = :patient_id
              AND timestamp BETWEEN :start_date AND :end_date
            ORDER BY timestamp ASC
        """

        rows = await self._fetch_all(
            query,
            {
                "patient_id": internal_patient_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "hormone_type",
                "hormone_context",
            ],
        )

        logger.info(
            "  Extracted %d hormonal/context records",
            len(df),
        )

        return df

    async def _extract_therapy_limits(
        self,
        internal_patient_id: str,
    ) -> pd.DataFrame:
        """
        Extract active therapy limits.

        Important:
            therapy_limits has no timestamp column.

        Therefore these records are configuration state, not time-series
        events. They are returned separately and anchored to the beginning
        of the requested training interval by the merge stage only when
        there is an actual active configuration.

        The database columns are:
            limit_type
            lower_bound
            upper_bound
            is_hard_limit
            time_of_day_start
            time_of_day_end
            day_of_week
            is_active
        """
        query = """
            SELECT
                limit_type,
                lower_bound,
                upper_bound,
                is_hard_limit,
                time_of_day_start,
                time_of_day_end,
                day_of_week
            FROM therapy_limits
            WHERE patient_id = :patient_id
              AND is_active = TRUE
            ORDER BY limit_type, time_of_day_start NULLS FIRST
        """

        rows = await self._fetch_all(
            query,
            {"patient_id": internal_patient_id},
        )

        if not rows:
            logger.info("  No active therapy limits found")
            return pd.DataFrame(
                columns=[
                    "therapy_limit_type",
                    "therapy_lower_bound",
                    "therapy_upper_bound",
                ]
            )

        # Keep the actual therapy configuration available without inventing
        # a timestamp that does not exist in the database.
        df = pd.DataFrame(rows)

        df = df.rename(
            columns={
                "limit_type": "therapy_limit_type",
                "lower_bound": "therapy_lower_bound",
                "upper_bound": "therapy_upper_bound",
            }
        )

        keep = [
            "therapy_limit_type",
            "therapy_lower_bound",
            "therapy_upper_bound",
        ]

        df = df[keep]

        logger.info(
            "  Extracted %d active therapy-limit records",
            len(df),
        )

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
        Merge time-series datasets.

        Therapy limits are configuration data and therefore are not merged
        by timestamp.
        """
        if glucose_df.empty:
            frames = [
                df
                for df in [
                    insulin_df,
                    carbs_df,
                    activity_df,
                    hormonal_df,
                ]
                if not df.empty
            ]

            if not frames:
                return TrainingDatasetBuilder._empty_dataset()

            df = frames[0].copy()

            for other_df in frames[1:]:
                df = pd.merge(
                    df,
                    other_df,
                    on="timestamp",
                    how="outer",
                )
        else:
            df = glucose_df.copy()

            for other_df, name in [
                (insulin_df, "insulin"),
                (carbs_df, "carbs"),
                (activity_df, "activity"),
                (hormonal_df, "hormonal"),
            ]:
                if not other_df.empty:
                    df = pd.merge(
                        df,
                        other_df,
                        on="timestamp",
                        how="outer",
                    )

                logger.debug(
                    "Merged %s: %d total records",
                    name,
                    len(df),
                )

        df = df.sort_values("timestamp").reset_index(drop=True)

        # Therapy limits have no timestamp. Do not fabricate one.
        # Preserve active therapy configuration as dataframe metadata.
        if not therapy_df.empty:
            df.attrs["therapy_limits"] = therapy_df.to_dict(
                orient="records"
            )
        else:
            df.attrs["therapy_limits"] = []

        return df

    @staticmethod
    def _resample_to_5min(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Resample time-series data to 5-minute intervals.

        Event columns use 'sum' so multiple events inside one 5-minute
        interval are not silently discarded.
        """
        df = df.copy()

        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
        )

        df = df.sort_values("timestamp")
        df.set_index("timestamp", inplace=True)

        event_columns = {
            "insulin_bolus_units",
            "insulin_basal_units",
            "carb_intake_grams",
        }

        aggregation = {}

        for column in df.columns:
            if column in event_columns:
                aggregation[column] = "sum"
            else:
                aggregation[column] = "first"

        df = df.resample(
            TrainingDatasetBuilder.RESAMPLE_INTERVAL
        ).agg(aggregation)

        df.reset_index(inplace=True)

        return df

    @staticmethod
    def _forward_fill_scalars(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Forward-fill scalar measurements.

        Event columns remain sparse.
        """
        df = df.copy()

        scalar_columns = [
            "glucose_mg_dl",
            "glucose_source",
            "insulin_basal_units",
        ]

        for column in scalar_columns:
            if column in df.columns:
                df[column] = df[column].ffill()

        return df

    @staticmethod
    def _empty_dataset() -> pd.DataFrame:
        """Return an empty dataframe with the canonical columns."""
        return pd.DataFrame(
            columns=[
                "timestamp",
                "glucose_mg_dl",
                "glucose_source",
                "insulin_bolus_units",
                "insulin_basal_units",
                "carb_intake_grams",
                "activity_intensity",
                "activity_duration_min",
                "hormone_type",
                "hormone_context",
            ]
        )

    def detect_gaps(
        self,
        df: pd.DataFrame,
        max_gap_minutes: int = MAX_GAP_MINUTES,
    ) -> List[DataGap]:
        """
        Detect gaps in glucose data greater than max_gap_minutes.
        """
        if df.empty:
            return []

        df = df.copy()

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
        )

        if "glucose_mg_dl" not in df.columns:
            return []

        df = df.sort_values("timestamp").reset_index(drop=True)

        has_glucose = df["glucose_mg_dl"].notna()

        gaps: List[DataGap] = []
        gap_start: Optional[int] = None

        for index in range(len(df)):
            if not has_glucose.iloc[index]:
                if gap_start is None:
                    gap_start = index
                continue

            if gap_start is None:
                continue

            gap_start_time = df.iloc[gap_start]["timestamp"]
            gap_end_time = df.iloc[index]["timestamp"]

            duration_minutes = (
                gap_end_time - gap_start_time
            ).total_seconds() / 60.0

            if duration_minutes > max_gap_minutes:
                gaps.append(
                    DataGap(
                        start_time=gap_start_time,
                        end_time=gap_end_time,
                        duration_minutes=duration_minutes,
                        gap_reason="unknown",
                    )
                )

            gap_start = None

        if gap_start is not None:
            gap_start_time = df.iloc[gap_start]["timestamp"]
            gap_end_time = df.iloc[-1]["timestamp"]

            duration_minutes = (
                gap_end_time - gap_start_time
            ).total_seconds() / 60.0

            if duration_minutes > max_gap_minutes:
                gaps.append(
                    DataGap(
                        start_time=gap_start_time,
                        end_time=gap_end_time,
                        duration_minutes=duration_minutes,
                        gap_reason="end_of_data",
                    )
                )

        logger.info(
            "Detected %d gaps > %d minutes",
            len(gaps),
            max_gap_minutes,
        )

        return gaps

    def compute_quality_metrics(
        self,
        df: pd.DataFrame,
    ) -> DataQualityMetrics:
        """
        Compute data-quality metrics for a Layer 1 dataset.
        """
        metrics = DataQualityMetrics()
        metrics.total_samples = len(df)

        if df.empty:
            return metrics

        if "glucose_mg_dl" in df.columns:
            metrics.missing_glucose_count = int(
                df["glucose_mg_dl"].isna().sum()
            )

            values = pd.to_numeric(
                df["glucose_mg_dl"],
                errors="coerce",
            )

            metrics.glucose_outlier_count = int(
                ((values < 40) | (values > 400)).sum()
            )

        if "insulin_bolus_units" in df.columns:
            metrics.missing_insulin_count = int(
                df["insulin_bolus_units"].isna().sum()
            )

            values = pd.to_numeric(
                df["insulin_bolus_units"],
                errors="coerce",
            )

            metrics.insulin_outlier_count = int(
                ((values < 0) | (values > 100)).sum()
            )

        if "carb_intake_grams" in df.columns:
            metrics.missing_carbs_count = int(
                df["carb_intake_grams"].isna().sum()
            )

        if "timestamp" in df.columns:
            metrics.duplicate_timestamp_count = int(
                df["timestamp"].duplicated().sum()
            )

        metrics.gaps = self.detect_gaps(df)

        logger.info(
            "Quality metrics: %s",
            metrics.to_dict(),
        )

        return metrics
