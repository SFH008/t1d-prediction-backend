"""
Phase 3 Layer 1: Full Integration Example

Demonstrates the complete Layer 1 pipeline:

1. Load database configuration from .env
2. Extract real patient data from PostgreSQL
3. Validate data quality
4. Chronologically split into train/val/test
5. Compute canonical features
6. Ready for Phase 3e (IOB trainer) or Phase 3f (LSTM trainer)

Database configuration:

    DATABASE_URL=postgresql+asyncpg://t1d_app:${POSTGRES_PASSWORD}@postgres:5432/t1d_glucose

The example runs on the host, so the Docker service hostname "postgres"
is converted to "localhost" for host-side execution.

Usage:

    python phase3_layer1_example.py

Optional:

    T1D_PATIENT_ID=<external_patient_id> python phase3_layer1_example.py
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Patient
from app.config import settings

from dotenv import load_dotenv

from app.ml.layer1.training_dataset_builder import TrainingDatasetBuilder
from app.ml.layer1.data_validator import DataValidator
from app.ml.layer1.chronological_splitter import (
    ChronologicalSplitter,
    TimeSeriesCrossValidator,
)
from app.ml.layer1.canonical_features import CanonicalFeatures


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Return the configured database URL."""

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set."
        )

    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "DATABASE_URL must use asyncpg. "
            f"Got {database_url!r}"
        )

    return database_url

async def get_external_patient_id() -> str:
    """Return the external patient ID from the database."""

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Patient.external_patient_id)
            .where(Patient.is_active.is_(True))
            .order_by(Patient.created_at)
            .limit(1)
        )

        patient_id = result.scalar_one_or_none()

        if patient_id is None:
            raise RuntimeError(
                "No active patient found in the database."
            )

        return patient_id


async def extract_real_dataset(
    database_url: str,
    patient_id: str,
    start_date: datetime,
    end_date: datetime,
):
    """Extract the real PostgreSQL dataset."""
    builder = TrainingDatasetBuilder(database_url)

    try:
        logger.info("=" * 80)
        logger.info("STEP 1: EXTRACT DATA FROM POSTGRESQL")
        logger.info("=" * 80)

        logger.info(
            "Database: PostgreSQL via asyncpg"
        )

        logger.info(
            "External patient ID: %s",
            patient_id,
        )

        logger.info(
            "Start: %s",
            start_date,
        )

        logger.info(
            "End:   %s",
            end_date,
        )

        raw_df = await builder.extract_patient_data(
            patient_id,
            start_date,
            end_date,
        )

        if raw_df.empty:
            raise RuntimeError(
                "PostgreSQL extraction returned no records. "
                "No synthetic data will be substituted."
            )

        logger.info(
            "Extracted %d records",
            len(raw_df),
        )

        logger.info(
            "Columns: %s",
            list(raw_df.columns),
        )

        if "timestamp" in raw_df.columns:
            logger.info(
                "Date range: %s → %s",
                raw_df["timestamp"].min(),
                raw_df["timestamp"].max(),
            )

        therapy_limits = raw_df.attrs.get(
            "therapy_limits",
            [],
        )

        logger.info(
            "Active therapy-limit configurations: %d",
            len(therapy_limits),
        )

        return raw_df

    finally:
        await builder.close()


def run_pipeline(
    raw_df,
):
    """
    Run validation, chronological splitting and canonical feature
    generation on the real database dataset.
    """

    # =======================================================================
    # STEP 2: VALIDATE DATA QUALITY
    # =======================================================================

    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: VALIDATE DATA QUALITY")
    logger.info("=" * 80)

    validator = DataValidator()
    validation_result = validator.validate(raw_df)

    logger.info(validation_result)

    validation_result.raise_if_invalid()

    logger.info("Data validation PASSED")

    # =======================================================================
    # STEP 3: CHRONOLOGICALLY SPLIT
    # =======================================================================

    logger.info("\n" + "=" * 80)
    logger.info(
        "STEP 3: CHRONOLOGICALLY SPLIT "
        "(prevent temporal leakage)"
    )
    logger.info("=" * 80)

    splitter = ChronologicalSplitter()

    train_df, val_df, test_df, split_info = splitter.split(
        raw_df,
        train_fraction=0.60,
        val_fraction=0.20,
        test_fraction=0.20,
    )

    logger.info(split_info)

    if not splitter.verify_no_leakage(
        train_df,
        val_df,
        test_df,
    ):
        raise RuntimeError(
            "Temporal leakage detected between train/validation/test data."
        )

    logger.info("Temporal leakage check PASSED")

    # =======================================================================
    # STEP 4: COMPUTE CANONICAL FEATURES
    # =======================================================================

    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: COMPUTE CANONICAL FEATURES")
    logger.info("=" * 80)

    feature_engineer = CanonicalFeatures()

    train_features = feature_engineer.compute(train_df)
    val_features = feature_engineer.compute(val_df)
    test_features = feature_engineer.compute(test_df)

    logger.info("Features computed for all splits")

    logger.info(
        "Train: %d samples × %d features",
        len(train_features),
        len(train_features.columns),
    )

    logger.info(
        "Val:   %d samples × %d features",
        len(val_features),
        len(val_features.columns),
    )

    logger.info(
        "Test:  %d samples × %d features",
        len(test_features),
        len(test_features.columns),
    )

    # =======================================================================
    # FEATURE GROUPS
    # =======================================================================

    logger.info("\nAvailable Feature Groups:")

    iob_features = feature_engineer.get_iob_features()
    lstm_features = feature_engineer.get_lstm_features()

    logger.info(
        "   IOB Trainer: %d features",
        len(iob_features),
    )

    logger.info(
        "     %s ...",
        iob_features[:5],
    )

    logger.info(
        "   LSTM Trainer: %d features",
        len(lstm_features),
    )

    logger.info(
        "     %s ...",
        lstm_features[:5],
    )

    # =======================================================================
    # STEP 5
    # =======================================================================

    logger.info("\n" + "=" * 80)
    logger.info(
        "STEP 5: READY FOR PHASE 3e (IOB) "
        "or 3f (LSTM) TRAINING"
    )
    logger.info("=" * 80)

    logger.info("")
    logger.info("IOB Trainer (Phase 3e) would receive:")
    logger.info(
        "   train_df[iob_features]: %s",
        train_features[iob_features].shape,
    )

    logger.info(
        "   Columns: %s...",
        list(train_features[iob_features].columns)[:7],
    )

    logger.info("")
    logger.info("LSTM Trainer (Phase 3f) would receive:")
    logger.info(
        "   train_df[lstm_features]: %s",
        train_features[lstm_features].shape,
    )

    logger.info(
        "   Columns: %s...",
        list(train_features[lstm_features].columns)[:7],
    )

    logger.info("\n" + "=" * 80)
    logger.info("LAYER 1 COMPLETE")
    logger.info("=" * 80)

    logger.info(
        "Successfully prepared real PostgreSQL data for model training:"
    )

    logger.info(
        "  • %d training samples",
        len(train_features),
    )

    logger.info(
        "  • %d validation samples",
        len(val_features),
    )

    logger.info(
        "  • %d test samples",
        len(test_features),
    )

    logger.info(
        "  • %d total features",
        len(train_features.columns),
    )

    logger.info("  • Zero temporal leakage")

    return (
        train_features,
        val_features,
        test_features,
    )


async def main():
    """Run the complete Layer 1 example."""

    database_url = get_database_url()
    patient_id = await get_external_patient_id()

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=90)

    raw_df = await extract_real_dataset(
        database_url,
        patient_id,
        start_date,
        end_date,
    )

    run_pipeline(raw_df)


if __name__ == "__main__":
    asyncio.run(main())
