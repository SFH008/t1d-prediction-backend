from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta


@dataclass(frozen=True)
class AbsorptionInterval:
    interval_start: datetime
    interval_end: datetime

    absorbed_carbs_grams: Decimal
    absorption_rate_g_per_min: Decimal

    cumulative_absorbed_grams: Decimal
    remaining_carbs_grams: Decimal

@dataclass(frozen=True)
class PatientAbsorptionInterval:
    interval_start: datetime
    interval_end: datetime

    base_absorbed_carbs_grams: Decimal

    hormonal_multiplier: Decimal
    activity_multiplier: Decimal

    adjusted_absorbed_carbs_grams: Decimal

    component_count: int

def generate_linear_absorption_curve(
    *,
    carbs_grams: Decimal,
    meal_timestamp: datetime,
    absorption_delay_minutes: int,
    absorption_duration_minutes: int,
    interval_minutes: int = 5,
) -> list[AbsorptionInterval]:
    """
    Generate a deterministic linear carbohydrate absorption curve.

    The component starts absorbing after absorption_delay_minutes and
    absorbs at a constant rate until absorption_duration_minutes have
    elapsed.

    The final interval may be shorter than interval_minutes so that the
    complete component is represented without changing its true duration.
    """

    carbs = Decimal(str(carbs_grams))

    if carbs < 0:
        raise ValueError("carbs_grams must be >= 0")

    if absorption_delay_minutes < 0:
        raise ValueError("absorption_delay_minutes must be >= 0")

    if absorption_duration_minutes <= 0:
        raise ValueError("absorption_duration_minutes must be > 0")

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    absorption_start = meal_timestamp + timedelta(
        minutes=absorption_delay_minutes
    )
    absorption_end = absorption_start + timedelta(
        minutes=absorption_duration_minutes
    )

    rate = carbs / Decimal(absorption_duration_minutes)

    intervals: list[AbsorptionInterval] = []
    current = absorption_start
    cumulative = Decimal("0")

    while current < absorption_end:
        interval_end = min(
            current + timedelta(minutes=interval_minutes),
            absorption_end,
        )

        actual_minutes = Decimal(
            str((interval_end - current).total_seconds() / 60)
        )

        absorbed = rate * actual_minutes

        # Make the final interval absorb the exact remainder. This avoids
        # accumulated Decimal representation differences.
        if interval_end == absorption_end:
            absorbed = carbs - cumulative

        cumulative += absorbed
        remaining = carbs - cumulative

        intervals.append(
            AbsorptionInterval(
                interval_start=current,
                interval_end=interval_end,
                absorbed_carbs_grams=absorbed,
                absorption_rate_g_per_min=rate,
                cumulative_absorbed_grams=cumulative,
                remaining_carbs_grams=remaining,
            )
        )

        current = interval_end

    return intervals

def aggregate_absorption_curves(
    *,
    curves: list[list[AbsorptionInterval]],
    window_start: datetime,
    window_end: datetime,
    interval_minutes: int = 5,
) -> list[PatientAbsorptionInterval]:
    """
    Aggregate multiple component absorption curves into a patient-level
    clock-aligned timeline.

    Component curves retain their true timestamps. Each patient interval
    receives only the proportional contribution that overlaps that interval.
    """

    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    interval_delta = timedelta(minutes=interval_minutes)

    # Align the first patient bucket to the previous real clock boundary.
    minute_floor = (
        window_start.minute // interval_minutes
    ) * interval_minutes

    aligned_start = window_start.replace(
        minute=minute_floor,
        second=0,
        microsecond=0,
    )

    patient_intervals: list[PatientAbsorptionInterval] = []
    bucket_start = aligned_start

    while bucket_start < window_end:
        bucket_end = bucket_start + interval_delta

        effective_start = max(bucket_start, window_start)
        effective_end = min(bucket_end, window_end)

        if effective_end <= effective_start:
            bucket_start = bucket_end
            continue

        base_absorbed = Decimal("0")
        contributing_components = 0

        for curve in curves:
            component_contributed = False

            for point in curve:
                overlap_start = max(
                    point.interval_start,
                    effective_start,
                )
                overlap_end = min(
                    point.interval_end,
                    effective_end,
                )

                if overlap_end <= overlap_start:
                    continue

                overlap_minutes = Decimal(
                    str(
                        (
                            overlap_end - overlap_start
                        ).total_seconds() / 60
                    )
                )

                contribution = (
                    point.absorption_rate_g_per_min
                    * overlap_minutes
                )

                base_absorbed += contribution
                component_contributed = True

            if component_contributed:
                contributing_components += 1

        hormonal_multiplier = Decimal("1.0")
        activity_multiplier = Decimal("1.0")

        adjusted_absorbed = (
            base_absorbed
            * hormonal_multiplier
            * activity_multiplier
        )

        patient_intervals.append(
            PatientAbsorptionInterval(
                interval_start=effective_start,
                interval_end=effective_end,
                base_absorbed_carbs_grams=base_absorbed,
                hormonal_multiplier=hormonal_multiplier,
                activity_multiplier=activity_multiplier,
                adjusted_absorbed_carbs_grams=adjusted_absorbed,
                component_count=contributing_components,
            )
        )

        bucket_start = bucket_end

    return patient_intervals

def next_complete_interval_start(
    timestamp: datetime,
    *,
    interval_minutes: int = 5,
) -> datetime:
    """
    Return the next complete clock-aligned interval boundary.

    Exact event timestamps remain unchanged elsewhere. This helper defines
    the standardized patient-level forecast grid.
    """

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    normalized = timestamp.replace(
        second=0,
        microsecond=0,
    )

    minute_remainder = normalized.minute % interval_minutes

    minutes_to_add = (
        interval_minutes
        if minute_remainder == 0
        else interval_minutes - minute_remainder
    )

    return normalized + timedelta(
        minutes=minutes_to_add
    )

def forecast_window(
    anchor_timestamp: datetime,
    *,
    horizon_hours: int = 6,
    interval_minutes: int = 5,
) -> tuple[datetime, datetime]:
    """
    Return the standardized forecast grid boundaries.

    The forecast starts at the next complete interval boundary and spans
    exactly horizon_hours using fixed interval_minutes buckets.
    """

    if horizon_hours <= 0:
        raise ValueError("horizon_hours must be > 0")

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    grid_start = next_complete_interval_start(
        anchor_timestamp,
        interval_minutes=interval_minutes,
    )

    grid_end = grid_start + timedelta(hours=horizon_hours)

    return grid_start, grid_end

def history_window(
    anchor_timestamp: datetime,
    *,
    history_hours: int = 6,
    interval_minutes: int = 5,
) -> tuple[datetime, datetime]:
    """
    Return the standardized historical grid boundaries.

    History ends at the same next complete interval boundary at which the
    forecast begins.
    """

    if history_hours <= 0:
        raise ValueError("history_hours must be > 0")

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    history_end = next_complete_interval_start(
        anchor_timestamp,
        interval_minutes=interval_minutes,
    )

    history_start = history_end - timedelta(
        hours=history_hours
    )

    return history_start, history_end