from datetime import datetime, time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.therapy_context import (
    TherapyContextError,
    resolve_therapy_context,
)


def profile(
    *,
    name="profile",
    start="09:00",
    end="13:30",
    isf=40,
    icr=10,
    target_min=90,
    target_max=110,
    day_of_week=None,
    active=True,
    created_at=None,
    basal_drift=0,
):
    return SimpleNamespace(
        id=uuid4(),
        profile_name=name,
        time_period_start=start,
        time_period_end=end,
        insulin_sensitivity_mg_dl_per_unit=Decimal(str(isf)),
        insulin_to_carb_ratio=Decimal(str(icr)),
        basal_drift_mg_dl_per_hour=Decimal(str(basal_drift)),
        target_glucose_min_mg_dl=(
            None if target_min is None else Decimal(str(target_min))
        ),
        target_glucose_max_mg_dl=(
            None if target_max is None else Decimal(str(target_max))
        ),
        day_of_week=day_of_week,
        is_active=active,
        created_at=created_at,
    )


def therapy_limit(
    *,
    lower=90,
    upper=110,
    start=None,
    end=None,
    day_of_week=None,
    active=True,
):
    return SimpleNamespace(
        id=uuid4(),
        limit_type="glucose_target",
        lower_bound=Decimal(str(lower)),
        upper_bound=Decimal(str(upper)),
        time_of_day_start=start,
        time_of_day_end=end,
        day_of_week=day_of_week,
        is_active=active,
        created_at=None,
    )


def test_selects_correct_time_of_day_profile():
    morning = profile(
        name="morning",
        start="06:00",
        end="10:00",
        isf=45,
        icr=12,
    )
    lunch = profile(
        name="lunch",
        start="10:00",
        end="14:00",
        isf=40,
        icr=10,
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 11, 30),
        time_of_day_profiles=[morning, lunch],
        therapy_limits=[],
    )

    assert context.carb_factor_g_per_unit == Decimal("10")
    assert context.insulin_sensitivity_mg_dl_per_unit == Decimal("40")
    assert context.target_glucose_mg_dl == Decimal("100")


def test_cross_midnight_profile_applies_after_midnight():
    overnight = profile(
        start="21:00",
        end="04:30",
        isf=50,
        icr=15,
        day_of_week=0,  # Sunday
    )

    context = resolve_therapy_context(
        # Monday 02:00, but still inside Sunday's overnight profile.
        meal_timestamp=datetime(2026, 8, 31, 2, 0),
        time_of_day_profiles=[overnight],
        therapy_limits=[],
    )

    assert context.carb_factor_g_per_unit == Decimal("15")
    assert context.insulin_sensitivity_mg_dl_per_unit == Decimal("50")


def test_exact_start_boundary_is_inclusive():
    item = profile(
        start="09:00",
        end="10:00",
        isf=40,
        icr=10,
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 9, 0),
        time_of_day_profiles=[item],
        therapy_limits=[],
    )

    assert context.carb_factor_g_per_unit == Decimal("10")


def test_exact_end_boundary_is_exclusive():
    item = profile(
        start="09:00",
        end="10:00",
    )

    with pytest.raises(TherapyContextError):
        resolve_therapy_context(
            meal_timestamp=datetime(2026, 9, 1, 10, 0),
            time_of_day_profiles=[item],
            therapy_limits=[],
        )


def test_inactive_profile_is_ignored():
    inactive = profile(active=False)

    with pytest.raises(TherapyContextError):
        resolve_therapy_context(
            meal_timestamp=datetime(2026, 9, 1, 10, 0),
            time_of_day_profiles=[inactive],
            therapy_limits=[],
        )


def test_day_of_week_uses_sunday_zero():
    sunday = profile(
        start="09:00",
        end="12:00",
        isf=55,
        icr=20,
        day_of_week=0,
    )

    context = resolve_therapy_context(
        # 2026-08-30 is Sunday.
        meal_timestamp=datetime(2026, 8, 30, 10, 0),
        time_of_day_profiles=[sunday],
        therapy_limits=[],
    )

    assert context.insulin_sensitivity_mg_dl_per_unit == Decimal("55")


def test_day_specific_profile_wins_over_all_days():
    generic = profile(
        name="generic",
        isf=50,
        icr=15,
        day_of_week=None,
        created_at=datetime(2026, 1, 1),
    )
    specific = profile(
        name="specific",
        isf=40,
        icr=10,
        day_of_week=2,  # Tuesday
        created_at=datetime(2026, 1, 2),
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 10, 0),
        time_of_day_profiles=[generic, specific],
        therapy_limits=[],
    )

    assert context.carb_factor_g_per_unit == Decimal("10")
    assert context.insulin_sensitivity_mg_dl_per_unit == Decimal("40")


def test_target_falls_back_to_therapy_limit():
    item = profile(
        target_min=None,
        target_max=None,
    )

    limit = therapy_limit(
        lower=90,
        upper=110,
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 10, 0),
        time_of_day_profiles=[item],
        therapy_limits=[limit],
    )

    assert context.target_glucose_mg_dl == Decimal("100")
    assert "target=therapy_limit" in context.source


def test_profile_target_range_uses_midpoint():
    item = profile(
        target_min=95,
        target_max=105,
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 10, 0),
        time_of_day_profiles=[item],
        therapy_limits=[],
    )

    assert context.target_glucose_mg_dl == Decimal("100")


def test_missing_therapy_configuration_fails():
    with pytest.raises(TherapyContextError):
        resolve_therapy_context(
            meal_timestamp=datetime(2026, 9, 1, 10, 0),
            time_of_day_profiles=[],
            therapy_limits=[],
        )


def test_decimal_values_are_preserved():
    item = profile(
        isf="42.50",
        icr="9.75",
        target_min="96.00",
        target_max="104.00",
    )

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 1, 10, 0),
        time_of_day_profiles=[item],
        therapy_limits=[],
    )

    assert context.carb_factor_g_per_unit == Decimal("9.75")
    assert context.insulin_sensitivity_mg_dl_per_unit == Decimal("42.50")
    assert context.target_glucose_mg_dl == Decimal("100.00")

def test_real_patient_band_boundaries_are_start_inclusive_end_exclusive():
    target = therapy_limit(lower=100, upper=100)
    bands = [
        profile(name="00:00", start="00:00", end="04:30", isf=200, icr=18, target_min=None, target_max=None),
        profile(name="04:30", start="04:30", end="09:00", isf=120, icr=12, target_min=None, target_max=None),
        profile(name="09:00", start="09:00", end="10:00", isf=150, icr=16, target_min=None, target_max=None),
        profile(name="10:00", start="10:00", end="11:30", isf=150, icr=16, target_min=None, target_max=None),
        profile(name="11:30", start="11:30", end="14:00", isf=120, icr=12, target_min=None, target_max=None),
        profile(name="14:00", start="14:00", end="16:30", isf=200, icr=18, target_min=None, target_max=None),
        profile(name="16:30", start="16:30", end="19:00", isf=150, icr=16, target_min=None, target_max=None),
        profile(name="19:00", start="19:00", end="21:00", isf=120, icr=12, target_min=None, target_max=None),
        profile(name="21:00", start="21:00", end="00:00", isf=150, icr=12, target_min=None, target_max=None),
    ]

    cases = [
        (datetime(2026, 9, 2, 4, 29), Decimal("18"), Decimal("200")),
        (datetime(2026, 9, 2, 4, 30), Decimal("12"), Decimal("120")),
        (datetime(2026, 9, 2, 11, 29), Decimal("16"), Decimal("150")),
        (datetime(2026, 9, 2, 11, 30), Decimal("12"), Decimal("120")),
        (datetime(2026, 9, 2, 20, 59), Decimal("12"), Decimal("120")),
        (datetime(2026, 9, 2, 21, 0), Decimal("12"), Decimal("150")),
        (datetime(2026, 9, 2, 23, 59), Decimal("12"), Decimal("150")),
        (datetime(2026, 9, 3, 0, 0), Decimal("18"), Decimal("200")),
    ]

    for timestamp, expected_icr, expected_isf in cases:
        context = resolve_therapy_context(
            meal_timestamp=timestamp,
            time_of_day_profiles=bands,
            therapy_limits=[target],
        )
        assert context.carb_factor_g_per_unit == expected_icr
        assert context.insulin_sensitivity_mg_dl_per_unit == expected_isf
        assert context.target_glucose_mg_dl == Decimal("100")


def test_therapy_context_includes_basal_drift_and_profile_id():
    item = profile(
        start="19:00",
        end="21:00",
        isf=120,
        icr=12,
        target_min=None,
        target_max=None,
        basal_drift="20",
    )
    target = therapy_limit(lower=100, upper=100)

    context = resolve_therapy_context(
        meal_timestamp=datetime(2026, 9, 2, 20, 0),
        time_of_day_profiles=[item],
        therapy_limits=[target],
    )

    assert context.basal_drift_mg_dl_per_hour == Decimal("20")
    assert context.profile_id == item.id
