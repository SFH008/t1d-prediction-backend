"""
Pure therapy-context resolution.

This module deliberately has no database dependency. It receives already-loaded
therapy configuration and deterministically resolves the values applicable at
a particular meal timestamp.
"""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class TherapyContext:
    """Immutable therapy inputs resolved for a specific timestamp."""

    carb_factor_g_per_unit: Decimal
    insulin_sensitivity_mg_dl_per_unit: Decimal
    target_glucose_mg_dl: Decimal
    basal_drift_mg_dl_per_hour: Decimal
    profile_id: object
    source: str


class TherapyContextError(ValueError):
    """Raised when therapy configuration cannot produce a valid context."""


def _as_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value

    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (AttributeError, TypeError, ValueError) as exc:
        raise TherapyContextError(
            f"Invalid therapy time value: {value!r}"
        ) from exc


def _schedule_day_of_week(timestamp: datetime, start: time, end: time) -> int:
    """
    Return the calendar day on which a time-of-day profile is anchored.

    Database convention:
        0 = Sunday
        1 = Monday
        ...
        6 = Saturday

    A profile crossing midnight belongs to its start day.
    """
    python_day = timestamp.weekday()  # Monday=0 ... Sunday=6

    # Convert Python Monday=0 to application Sunday=0.
    current_day = (python_day + 1) % 7

    if start > end and timestamp.time() < end:
        # We are in the after-midnight portion of a profile that started
        # yesterday.
        return (current_day - 1) % 7

    return current_day


def _time_matches(
    timestamp: datetime,
    start: time,
    end: time,
) -> bool:
    """Start-inclusive, end-exclusive time matching."""
    current = timestamp.time()

    if start < end:
        return start <= current < end

    if start > end:
        return current >= start or current < end

    # Equal start/end represents a full-day profile.
    return True


def _profile_matches(profile, timestamp: datetime) -> bool:
    if not getattr(profile, "is_active", True):
        return False

    start = _parse_time(profile.time_period_start)
    end = _parse_time(profile.time_period_end)

    if not _time_matches(timestamp, start, end):
        return False

    profile_day = getattr(profile, "day_of_week", None)

    if profile_day is None:
        return True

    return profile_day == _schedule_day_of_week(timestamp, start, end)


def _profile_sort_key(profile):
    """
    Deterministic ordering for overlapping profiles.

    More specific day-of-week profiles win over all-days profiles.
    Earlier-created records win the remaining tie.
    """
    day_specific = getattr(profile, "day_of_week", None) is not None
    created_at = getattr(profile, "created_at", None)

    return (
        0 if day_specific else 1,
        created_at if created_at is not None else datetime.min,
        str(getattr(profile, "id", "")),
    )


def _matching_profiles(
    profiles: Iterable,
    timestamp: datetime,
) -> list:
    matches = [
        profile
        for profile in profiles
        if _profile_matches(profile, timestamp)
    ]

    return sorted(matches, key=_profile_sort_key)


def _matching_target_limits(
    therapy_limits: Iterable,
    timestamp: datetime,
) -> list:
    """
    Find active glucose-target limits applicable at timestamp.

    TherapyLimit uses:
        0 = Sunday ... 6 = Saturday
    """
    current = timestamp.time()
    current_day = (timestamp.weekday() + 1) % 7

    matches = []

    for limit in therapy_limits:
        if not getattr(limit, "is_active", True):
            continue

        if getattr(limit, "limit_type", None) != "glucose_target":
            continue

        day = getattr(limit, "day_of_week", None)
        if day is not None and day != current_day:
            continue

        start = getattr(limit, "time_of_day_start", None)
        end = getattr(limit, "time_of_day_end", None)

        if start is None or end is None:
            matches.append(limit)
            continue

        if _time_matches(timestamp, start, end):
            matches.append(limit)

    return sorted(
        matches,
        key=lambda item: (
            getattr(item, "created_at", None)
            if getattr(item, "created_at", None) is not None
            else datetime.min,
            str(getattr(item, "id", "")),
        ),
    )


def _target_from_profile(profile) -> Decimal | None:
    minimum = _as_decimal(
        getattr(profile, "target_glucose_min_mg_dl", None)
    )
    maximum = _as_decimal(
        getattr(profile, "target_glucose_max_mg_dl", None)
    )

    if minimum is not None and maximum is not None:
        return (minimum + maximum) / Decimal("2")

    if minimum is not None:
        return minimum

    if maximum is not None:
        return maximum

    return None


def _target_from_limit(limit) -> Decimal | None:
    lower = _as_decimal(getattr(limit, "lower_bound", None))
    upper = _as_decimal(getattr(limit, "upper_bound", None))

    if lower is not None and upper is not None:
        return (lower + upper) / Decimal("2")

    return lower if lower is not None else upper


def resolve_therapy_context(
    *,
    meal_timestamp: datetime,
    time_of_day_profiles: Iterable,
    therapy_limits: Iterable,
    settings=None,
) -> TherapyContext:
    """
    Resolve deterministic therapy inputs for a meal timestamp.

    Required:
        - applicable ICR
        - applicable ISF
        - applicable target glucose

    No database access or mutation occurs here.
    """
    del settings  # Reserved until override_sensitivity_factor semantics are defined.

    profiles = _matching_profiles(
        time_of_day_profiles,
        meal_timestamp,
    )

    if not profiles:
        raise TherapyContextError(
            "No active time-of-day therapy profile applies to "
            f"{meal_timestamp.isoformat()}"
        )

    profile = profiles[0]

    isf = _as_decimal(
        profile.insulin_sensitivity_mg_dl_per_unit
    )
    icr = _as_decimal(
        profile.insulin_to_carb_ratio
    )

    if isf is None or isf <= 0:
        raise TherapyContextError(
            "Applicable therapy profile has no valid insulin sensitivity"
        )

    if icr is None or icr <= 0:
        raise TherapyContextError(
            "Applicable therapy profile has no valid insulin-to-carb ratio"
        )

    target = _target_from_profile(profile)

    target_source = "time_of_day_profile"

    if target is None:
        limits = _matching_target_limits(
            therapy_limits,
            meal_timestamp,
        )

        if limits:
            target = _target_from_limit(limits[0])
            target_source = "therapy_limit"

    if target is None or target <= 0:
        raise TherapyContextError(
            "No valid target glucose is configured for "
            f"{meal_timestamp.isoformat()}"
        )

    basal_drift = _as_decimal(
        getattr(profile, "basal_drift_mg_dl_per_hour", 0)
    )
    if basal_drift is None:
        basal_drift = Decimal("0")

    return TherapyContext(
        carb_factor_g_per_unit=icr,
        insulin_sensitivity_mg_dl_per_unit=isf,
        target_glucose_mg_dl=target,
        basal_drift_mg_dl_per_hour=basal_drift,
        profile_id=getattr(profile, "id", None),
        source=(
            f"time_of_day_profile:{profile.id}:"
            f"target={target_source}"
        ),
    )