"""
Patient absorption timeline orchestration helpers.

This module bridges immutable meal-component absorption snapshots to the
pure deterministic curve engine and coordinates persistence of historical
and forecast patient absorption timelines.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.models import (
    Meal,
    MealCarbGroup,
    MealComponentAbsorption,
)
from app.services.absorption_curve import (
    PatientAbsorptionInterval,
    aggregate_absorption_curves,
    forecast_window,
    generate_linear_absorption_curve,
    history_window,
)
from app.services.absorption_persistence import (
    stage_absorption_history,
    stage_current_forecast,
)


@dataclass(frozen=True)
class PatientAbsorptionTimeline:
    """
    Complete deterministic patient absorption timeline around one anchor.

    History and forecast each contain exactly 72 clock-aligned
    five-minute intervals.
    """

    anchor_timestamp: datetime

    history_start: datetime
    history_end: datetime

    forecast_start: datetime
    forecast_end: datetime

    history: list[PatientAbsorptionInterval]
    forecast: list[PatientAbsorptionInterval]


@dataclass(frozen=True)
class PersistedPatientAbsorptionTimeline:
    """
    ORM rows staged or persisted for one patient absorption timeline.
    """

    history_rows: list
    forecast_rows: list


@dataclass(frozen=True)
class RebuiltPatientAbsorptionTimeline:
    """
    Result of building and persisting a patient absorption timeline.
    """

    timeline: PatientAbsorptionTimeline
    persisted: PersistedPatientAbsorptionTimeline


def build_component_curves(
    *,
    components,
):
    """
    Build deterministic curves from immutable component snapshots.

    The curve uses:
      - Meal.meal_timestamp
      - MealCarbGroup.carbs_grams
      - snapshotted absorption delay
      - snapshotted absorption duration

    Current deterministic baseline supports only the linear curve type.
    """

    curves = []

    for component in components:
        if component.curve_type != "linear":
            raise ValueError(
                f"Unsupported curve_type: {component.curve_type}"
            )

        meal_group = component.meal_carb_group
        meal = meal_group.meal

        curve_carbs_grams = (
            meal_group.carbs_grams
            if meal_group.consumed_carbs_grams is None
            else meal_group.consumed_carbs_grams
        )

        curve = generate_linear_absorption_curve(
            carbs_grams=curve_carbs_grams,
            meal_timestamp=meal.meal_timestamp,
            absorption_delay_minutes=(
                component.absorption_delay_minutes
            ),
            absorption_duration_minutes=(
                component.absorption_duration_minutes
            ),
            interval_minutes=5,
        )

        curves.append(curve)

    return curves


def component_overlaps_window(
    *,
    component,
    window_start,
    window_end,
) -> bool:
    """
    Return whether one component absorption window overlaps a requested
    patient timeline window.

    Both intervals are treated as half-open:

        [absorption_start, absorption_end)
        [window_start, window_end)

    Therefore a component ending exactly at window_start does not overlap,
    and one starting exactly at window_end does not overlap.
    """

    meal_timestamp = (
        component.meal_carb_group.meal.meal_timestamp
    )

    absorption_start = meal_timestamp + timedelta(
        minutes=component.absorption_delay_minutes
    )

    absorption_end = absorption_start + timedelta(
        minutes=component.absorption_duration_minutes
    )

    return (
        absorption_start < window_end
        and absorption_end > window_start
    )


async def load_overlapping_components(
    *,
    db,
    patient_id,
    window_start,
    window_end,
):
    """
    Load immutable meal-component absorption snapshots that overlap the
    requested patient timeline window.

    SQL performs patient isolation and a conservative meal-time bound.
    Exact absorption overlap is evaluated by component_overlaps_window()
    using the snapshotted delay and duration.

    MealCarbGroup and Meal are eagerly loaded so deterministic curve
    construction does not require async lazy-loading.
    """

    if window_end <= window_start:
        raise ValueError(
            "window_end must be after window_start"
        )

    stmt = (
        select(MealComponentAbsorption)
        .join(
            MealCarbGroup,
            MealComponentAbsorption.meal_carb_group_id
            == MealCarbGroup.id,
        )
        .join(
            Meal,
            MealCarbGroup.meal_id == Meal.id,
        )
        .options(
            joinedload(
                MealComponentAbsorption.meal_carb_group
            ).joinedload(
                MealCarbGroup.meal
            )
        )
        .where(
            MealComponentAbsorption.patient_id == patient_id,
            Meal.meal_timestamp < window_end,
        )
        .order_by(
            Meal.meal_timestamp,
            MealComponentAbsorption.id,
        )
    )

    result = await db.execute(stmt)

    candidates = result.scalars().all()

    return [
        component
        for component in candidates
        if component_overlaps_window(
            component=component,
            window_start=window_start,
            window_end=window_end,
        )
    ]


async def build_patient_absorption_timeline(
    *,
    db,
    patient_id,
    anchor_timestamp,
) -> PatientAbsorptionTimeline:
    """
    Build the deterministic six-hour historical and six-hour forecast
    absorption timelines for one patient.

    The exact anchor timestamp is retained, while both persisted/display
    timelines use standardized five-minute clock boundaries.
    """

    history_start, history_end = history_window(
        anchor_timestamp
    )

    forecast_start, forecast_end = forecast_window(
        anchor_timestamp
    )

    history_components = await load_overlapping_components(
        db=db,
        patient_id=patient_id,
        window_start=history_start,
        window_end=history_end,
    )

    forecast_components = await load_overlapping_components(
        db=db,
        patient_id=patient_id,
        window_start=forecast_start,
        window_end=forecast_end,
    )

    history_curves = build_component_curves(
        components=history_components
    )

    forecast_curves = build_component_curves(
        components=forecast_components
    )

    history = aggregate_absorption_curves(
        curves=history_curves,
        window_start=history_start,
        window_end=history_end,
        interval_minutes=5,
    )

    forecast = aggregate_absorption_curves(
        curves=forecast_curves,
        window_start=forecast_start,
        window_end=forecast_end,
        interval_minutes=5,
    )

    if len(history) != 72:
        raise ValueError(
            "historical absorption timeline must contain "
            "exactly 72 intervals"
        )

    if len(forecast) != 72:
        raise ValueError(
            "forecast absorption timeline must contain "
            "exactly 72 intervals"
        )

    return PatientAbsorptionTimeline(
        anchor_timestamp=anchor_timestamp,
        history_start=history_start,
        history_end=history_end,
        forecast_start=forecast_start,
        forecast_end=forecast_end,
        history=history,
        forecast=forecast,
    )


async def stage_patient_absorption_timeline(
    *,
    db,
    patient_id,
    timeline: PatientAbsorptionTimeline,
    derivation_model: str = "deterministic_linear",
    derivation_version: str = "deterministic_linear_v1",
    derivation_mode: str = "original",
) -> PersistedPatientAbsorptionTimeline:
    """
    Stage historical absorption and current forecast without committing.

    Historical staging is idempotent for an existing identical derivation.
    Forecast staging replaces the patient's current operational forecast.

    The caller owns the surrounding transaction.
    """

    history_rows = await stage_absorption_history(
        db=db,
        patient_id=patient_id,
        timeline=timeline.history,
        derivation_model=derivation_model,
        derivation_version=derivation_version,
        derivation_mode=derivation_mode,
    )

    forecast_rows = await stage_current_forecast(
        db=db,
        patient_id=patient_id,
        forecast_anchor_timestamp=timeline.anchor_timestamp,
        forecast_grid_start=timeline.forecast_start,
        timeline=timeline.forecast,
    )

    return PersistedPatientAbsorptionTimeline(
        history_rows=history_rows,
        forecast_rows=forecast_rows,
    )


async def persist_patient_absorption_timeline(
    *,
    db,
    patient_id,
    timeline: PatientAbsorptionTimeline,
    derivation_model: str = "deterministic_linear",
    derivation_version: str = "deterministic_linear_v1",
    derivation_mode: str = "original",
) -> PersistedPatientAbsorptionTimeline:
    """
    Persist historical absorption and current forecast as one transaction.

    This wrapper owns commit/rollback. Call
    stage_patient_absorption_timeline() when a larger transaction, such as
    meal capture, must own the commit boundary.
    """

    try:
        result = await stage_patient_absorption_timeline(
            db=db,
            patient_id=patient_id,
            timeline=timeline,
            derivation_model=derivation_model,
            derivation_version=derivation_version,
            derivation_mode=derivation_mode,
        )

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    return result


async def rebuild_patient_absorption_timeline(
    *,
    db,
    patient_id,
    anchor_timestamp,
) -> RebuiltPatientAbsorptionTimeline:
    """
    Build and atomically persist the patient's deterministic absorption
    history and current forecast for an exact anchor timestamp.

    This operation owns its persistence transaction. API operations that
    need a larger transaction boundary should call:

        build_patient_absorption_timeline()
        stage_patient_absorption_timeline()

    and commit themselves.
    """

    timeline = await build_patient_absorption_timeline(
        db=db,
        patient_id=patient_id,
        anchor_timestamp=anchor_timestamp,
    )

    persisted = await persist_patient_absorption_timeline(
        db=db,
        patient_id=patient_id,
        timeline=timeline,
    )

    return RebuiltPatientAbsorptionTimeline(
        timeline=timeline,
        persisted=persisted,
    )