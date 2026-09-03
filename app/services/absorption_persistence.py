"""
Persistence for the current deterministic patient absorption forecast.

The current forecast is operational state. Replacement is performed as one
database transaction so an unsuccessful replacement cannot leave a patient
with a partially updated forecast.
"""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PatientAbsorptionForecast,
    PatientAbsorptionHistory,
)
from app.services.absorption_curve import PatientAbsorptionInterval


FORECAST_BUCKET_COUNT = 72
FORECAST_INTERVAL_MINUTES = 5
DETERMINISTIC_MODEL_VERSION = "deterministic_linear_v1"


def _validate_forecast_grid(
    *,
    forecast_grid_start,
    timeline: list[PatientAbsorptionInterval],
) -> None:
    """
    Validate a complete six-hour, five-minute forecast grid before any
    destructive database operation is performed.
    """

    if len(timeline) != FORECAST_BUCKET_COUNT:
        raise ValueError(
            "forecast timeline must contain exactly 72 intervals"
        )

    interval_delta = timedelta(
        minutes=FORECAST_INTERVAL_MINUTES
    )

    expected_start = forecast_grid_start

    for point in timeline:
        expected_end = expected_start + interval_delta

        if (
            point.interval_start != expected_start
            or point.interval_end != expected_end
        ):
            raise ValueError(
                "forecast timeline does not match forecast grid"
            )

        expected_start = expected_end

async def stage_current_forecast(
    *,
    db: AsyncSession,
    patient_id: UUID,
    forecast_anchor_timestamp,
    forecast_grid_start,
    timeline: list[PatientAbsorptionInterval],
) -> list[PatientAbsorptionForecast]:
    """
    Stage replacement of a patient's current forecast without committing.

    Caller owns the surrounding transaction.
    """

    _validate_forecast_grid(
        forecast_grid_start=forecast_grid_start,
        timeline=timeline,
    )

    rows = [
        PatientAbsorptionForecast(
            patient_id=patient_id,
            forecast_anchor_timestamp=forecast_anchor_timestamp,
            forecast_grid_start=forecast_grid_start,
            interval_start=point.interval_start,
            interval_end=point.interval_end,
            base_absorbed_carbs_grams=point.base_absorbed_carbs_grams,
            hormonal_multiplier=point.hormonal_multiplier,
            activity_multiplier=point.activity_multiplier,
            adjusted_absorbed_carbs_grams=(
                point.adjusted_absorbed_carbs_grams
            ),
            component_count=point.component_count,
            deterministic_model_version=(
                DETERMINISTIC_MODEL_VERSION
            ),
        )
        for point in timeline
    ]

    await db.execute(
        delete(PatientAbsorptionForecast).where(
            PatientAbsorptionForecast.patient_id == patient_id
        )
    )

    db.add_all(rows)

    return rows

async def replace_current_forecast(
    *,
    db: AsyncSession,
    patient_id: UUID,
    forecast_anchor_timestamp,
    forecast_grid_start,
    timeline: list[PatientAbsorptionInterval],
) -> list[PatientAbsorptionForecast]:
    """
    Atomically replace a patient's current 72-point absorption forecast.
    """

    try:
        rows = await stage_current_forecast(
            db=db,
            patient_id=patient_id,
            forecast_anchor_timestamp=forecast_anchor_timestamp,
            forecast_grid_start=forecast_grid_start,
            timeline=timeline,
        )

        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise

    return rows

def _validate_history_grid(
    timeline: list[PatientAbsorptionInterval],
) -> None:
    interval_delta = timedelta(
        minutes=FORECAST_INTERVAL_MINUTES
    )

    for point in timeline:
        if (
            point.interval_end
            != point.interval_start + interval_delta
        ):
            raise ValueError(
                "history grid intervals must be exactly 5 minutes"
            )

        if (
            point.interval_start.second != 0
            or point.interval_start.microsecond != 0
            or point.interval_start.minute
            % FORECAST_INTERVAL_MINUTES
            != 0
        ):
            raise ValueError(
                "history grid must use clock-aligned 5-minute intervals"
            )

FORECAST_BUCKET_COUNT = 72
FORECAST_INTERVAL_MINUTES = 5
DETERMINISTIC_MODEL_VERSION = "deterministic_linear_v1"

VALID_DERIVATION_MODES = {
    "original",
    "retrospective",
}

def stage_absorption_history(
    *,
    db: AsyncSession,
    patient_id: UUID,
    timeline: list[PatientAbsorptionInterval],
    derivation_model: str,
    derivation_version: str,
    derivation_mode: str,
) -> list[PatientAbsorptionHistory]:
    """
    Stage versioned historical absorption estimates without committing.

    Caller owns the surrounding transaction.
    """

    if derivation_mode not in VALID_DERIVATION_MODES:
        raise ValueError(
            "derivation_mode must be original or retrospective"
        )

    _validate_history_grid(timeline)

    rows = [
        PatientAbsorptionHistory(
            patient_id=patient_id,
            interval_start=point.interval_start,
            interval_end=point.interval_end,
            base_absorbed_carbs_grams=(
                point.base_absorbed_carbs_grams
            ),
            hormonal_multiplier=point.hormonal_multiplier,
            activity_multiplier=point.activity_multiplier,
            adjusted_absorbed_carbs_grams=(
                point.adjusted_absorbed_carbs_grams
            ),
            component_count=point.component_count,
            derivation_model=derivation_model,
            derivation_version=derivation_version,
            derivation_mode=derivation_mode,
        )
        for point in timeline
    ]

    db.add_all(rows)

    return rows

async def persist_absorption_history(
    *,
    db: AsyncSession,
    patient_id: UUID,
    timeline: list[PatientAbsorptionInterval],
    derivation_model: str,
    derivation_version: str,
    derivation_mode: str,
) -> list[PatientAbsorptionHistory]:
    """
    Persist versioned historical absorption estimates.
    """

    try:
        rows = stage_absorption_history(
            db=db,
            patient_id=patient_id,
            timeline=timeline,
            derivation_model=derivation_model,
            derivation_version=derivation_version,
            derivation_mode=derivation_mode,
        )

        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise

    return rows