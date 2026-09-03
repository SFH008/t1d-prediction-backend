from datetime import datetime, timedelta
from decimal import Decimal

from app.services.absorption_curve import (
    aggregate_absorption_curves,
    forecast_window,
    history_window,
    generate_linear_absorption_curve,
    next_complete_interval_start,
)

def test_linear_curve_uses_delay_then_duration():
    meal_timestamp = datetime(2026, 9, 3, 12, 0)

    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=meal_timestamp,
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    assert curve[0].interval_start == datetime(2026, 9, 3, 12, 10)
    assert curve[-1].interval_end == datetime(2026, 9, 3, 13, 10)


def test_linear_curve_has_expected_interval_count():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    assert len(curve) == 12


def test_linear_curve_distributes_carbs_evenly():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    assert all(
        point.absorbed_carbs_grams == Decimal("2.5")
        for point in curve
    )


def test_linear_curve_preserves_total_carbohydrate_mass():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    total = sum(
        point.absorbed_carbs_grams
        for point in curve
    )

    assert total == Decimal("30")

import pytest


def test_linear_curve_handles_partial_final_interval():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("17"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=17,
        interval_minutes=5,
    )

    assert len(curve) == 4

    assert curve[0].absorbed_carbs_grams == Decimal("5")
    assert curve[1].absorbed_carbs_grams == Decimal("5")
    assert curve[2].absorbed_carbs_grams == Decimal("5")
    assert curve[3].absorbed_carbs_grams == Decimal("2")

    assert curve[-1].interval_end == datetime(2026, 9, 3, 12, 27)

    total = sum(
        point.absorbed_carbs_grams
        for point in curve
    )

    assert total == Decimal("17")


def test_linear_curve_zero_carbs_produces_zero_absorption():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("0"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    assert len(curve) == 12
    assert all(
        point.absorbed_carbs_grams == Decimal("0")
        for point in curve
    )
    assert all(
        point.remaining_carbs_grams == Decimal("0")
        for point in curve
    )


def test_linear_curve_rejects_negative_carbs():
    with pytest.raises(ValueError):
        generate_linear_absorption_curve(
            carbs_grams=Decimal("-1"),
            meal_timestamp=datetime(2026, 9, 3, 12, 0),
            absorption_delay_minutes=10,
            absorption_duration_minutes=60,
        )


def test_linear_curve_rejects_negative_delay():
    with pytest.raises(ValueError):
        generate_linear_absorption_curve(
            carbs_grams=Decimal("10"),
            meal_timestamp=datetime(2026, 9, 3, 12, 0),
            absorption_delay_minutes=-1,
            absorption_duration_minutes=60,
        )


def test_linear_curve_rejects_non_positive_duration():
    for duration in (0, -1):
        with pytest.raises(ValueError):
            generate_linear_absorption_curve(
                carbs_grams=Decimal("10"),
                meal_timestamp=datetime(2026, 9, 3, 12, 0),
                absorption_delay_minutes=10,
                absorption_duration_minutes=duration,
            )


def test_linear_curve_rejects_non_positive_interval():
    for interval in (0, -5):
        with pytest.raises(ValueError):
            generate_linear_absorption_curve(
                carbs_grams=Decimal("10"),
                meal_timestamp=datetime(2026, 9, 3, 12, 0),
                absorption_delay_minutes=10,
                absorption_duration_minutes=60,
                interval_minutes=interval,
            )


def test_linear_curve_remaining_carbs_never_negative():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
    )

    assert all(
        point.remaining_carbs_grams >= Decimal("0")
        for point in curve
    )

    assert curve[-1].remaining_carbs_grams == Decimal("0")

def test_aggregate_overlapping_component_curves():
    meal_time = datetime(2026, 9, 3, 12, 0)

    fast_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=meal_time,
        absorption_delay_minutes=0,
        absorption_duration_minutes=60,
        interval_minutes=5,
    )

    slow_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("60"),
        meal_timestamp=meal_time,
        absorption_delay_minutes=0,
        absorption_duration_minutes=120,
        interval_minutes=5,
    )

    timeline = aggregate_absorption_curves(
        curves=[fast_curve, slow_curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 13, 0),
        interval_minutes=5,
    )

    assert len(timeline) == 12

    # fast: 30 / 60 = 0.5 g/min
    # slow: 60 / 120 = 0.5 g/min
    # total = 1.0 g/min = 5.0 g per 5 min
    assert all(
        point.base_absorbed_carbs_grams == Decimal("5.0")
        for point in timeline
    )

    assert all(
        point.component_count == 2
        for point in timeline
    )


def test_aggregate_non_overlapping_components():
    first_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=0,
        absorption_duration_minutes=30,
    )

    second_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 30),
        absorption_delay_minutes=0,
        absorption_duration_minutes=30,
    )

    timeline = aggregate_absorption_curves(
        curves=[first_curve, second_curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 13, 0),
    )

    assert len(timeline) == 12
    assert all(
        point.component_count == 1
        for point in timeline
    )


def test_aggregate_includes_previous_meal_still_active():
    previous_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("60"),
        meal_timestamp=datetime(2026, 9, 3, 11, 0),
        absorption_delay_minutes=0,
        absorption_duration_minutes=180,
    )

    new_curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=0,
        absorption_duration_minutes=60,
    )

    timeline = aggregate_absorption_curves(
        curves=[previous_curve, new_curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 13, 0),
    )

    assert all(
        point.component_count == 2
        for point in timeline
    )


def test_aggregate_uses_clock_aligned_buckets_with_partial_overlap():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("20"),
        meal_timestamp=datetime(2026, 9, 3, 12, 2),
        absorption_delay_minutes=0,
        absorption_duration_minutes=20,
    )

    timeline = aggregate_absorption_curves(
        curves=[curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 12, 25),
        interval_minutes=5,
    )

    assert timeline[0].interval_start == datetime(2026, 9, 3, 12, 0)
    assert timeline[0].interval_end == datetime(2026, 9, 3, 12, 5)

    # rate = 1 g/min, overlap 12:02–12:05 = 3 min
    assert timeline[0].base_absorbed_carbs_grams == Decimal("3.0")

    assert timeline[1].base_absorbed_carbs_grams == Decimal("5.0")
    assert timeline[2].base_absorbed_carbs_grams == Decimal("5.0")
    assert timeline[3].base_absorbed_carbs_grams == Decimal("5.0")

    # final overlap 12:20–12:22 = 2 min
    assert timeline[4].base_absorbed_carbs_grams == Decimal("2.0")


def test_aggregate_multipliers_are_neutral_baseline():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=0,
        absorption_duration_minutes=60,
    )

    timeline = aggregate_absorption_curves(
        curves=[curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 13, 0),
    )

    assert all(
        point.hormonal_multiplier == Decimal("1.0")
        for point in timeline
    )

    assert all(
        point.activity_multiplier == Decimal("1.0")
        for point in timeline
    )

    assert all(
        point.adjusted_absorbed_carbs_grams
        == point.base_absorbed_carbs_grams
        for point in timeline
    )


def test_aggregate_preserves_mass_inside_requested_window():
    curve = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=0,
        absorption_duration_minutes=60,
    )

    timeline = aggregate_absorption_curves(
        curves=[curve],
        window_start=datetime(2026, 9, 3, 12, 0),
        window_end=datetime(2026, 9, 3, 13, 0),
    )

    total = sum(
        point.base_absorbed_carbs_grams
        for point in timeline
    )

    assert total == Decimal("30")

def test_six_hour_forecast_contains_72_intervals():
    anchor = datetime(2026, 9, 3, 12, 0)

    timeline = aggregate_absorption_curves(
        curves=[],
        window_start=anchor,
        window_end=anchor + timedelta(hours=6),
        interval_minutes=5,
    )

    assert len(timeline) == 72

    assert timeline[0].interval_start == anchor
    assert timeline[0].interval_end == datetime(2026, 9, 3, 12, 5)

    assert timeline[-1].interval_start == datetime(2026, 9, 3, 17, 55)
    assert timeline[-1].interval_end == datetime(2026, 9, 3, 18, 0)


def test_new_forecast_keeps_absorption_from_previous_meal():
    previous_meal = generate_linear_absorption_curve(
        carbs_grams=Decimal("60"),
        meal_timestamp=datetime(2026, 9, 3, 10, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=300,
    )

    new_meal = generate_linear_absorption_curve(
        carbs_grams=Decimal("30"),
        meal_timestamp=datetime(2026, 9, 3, 12, 0),
        absorption_delay_minutes=10,
        absorption_duration_minutes=60,
    )

    anchor = datetime(2026, 9, 3, 12, 0)

    timeline = aggregate_absorption_curves(
        curves=[previous_meal, new_meal],
        window_start=anchor,
        window_end=anchor + timedelta(hours=6),
        interval_minutes=5,
    )

    assert len(timeline) == 72

    # 12:00-12:05:
    # previous meal is already absorbing;
    # new meal remains in its 10-minute delay.
    assert timeline[0].component_count == 1

    # 12:10-12:15:
    # both meals are now absorbing.
    assert timeline[2].component_count == 2


def test_next_complete_interval_start_rounds_forward():
    assert next_complete_interval_start(
        datetime(2026, 9, 3, 12, 37)
    ) == datetime(2026, 9, 3, 12, 40)


def test_next_complete_interval_start_moves_from_exact_boundary():
    assert next_complete_interval_start(
        datetime(2026, 9, 3, 12, 40)
    ) == datetime(2026, 9, 3, 12, 45)


def test_next_complete_interval_start_handles_seconds():
    assert next_complete_interval_start(
        datetime(2026, 9, 3, 12, 40, 1)
    ) == datetime(2026, 9, 3, 12, 45)


def test_next_complete_interval_start_crosses_hour():
    assert next_complete_interval_start(
        datetime(2026, 9, 3, 12, 59)
    ) == datetime(2026, 9, 3, 13, 0)


def test_next_complete_interval_start_rejects_invalid_interval():
    with pytest.raises(ValueError):
        next_complete_interval_start(
            datetime(2026, 9, 3, 12, 37),
            interval_minutes=0,
        )

def test_forecast_window_from_arbitrary_anchor():
    grid_start, grid_end = forecast_window(
        datetime(2026, 9, 3, 12, 37)
    )

    assert grid_start == datetime(2026, 9, 3, 12, 40)
    assert grid_end == datetime(2026, 9, 3, 18, 40)


def test_forecast_window_produces_exactly_72_buckets():
    anchor = datetime(2026, 9, 3, 12, 37)

    grid_start, grid_end = forecast_window(anchor)

    timeline = aggregate_absorption_curves(
        curves=[],
        window_start=grid_start,
        window_end=grid_end,
        interval_minutes=5,
    )

    assert len(timeline) == 72


def test_forecast_window_moves_from_exact_boundary():
    grid_start, grid_end = forecast_window(
        datetime(2026, 9, 3, 12, 40)
    )

    assert grid_start == datetime(2026, 9, 3, 12, 45)
    assert grid_end == datetime(2026, 9, 3, 18, 45)


def test_forecast_window_rejects_invalid_horizon():
    with pytest.raises(ValueError):
        forecast_window(
            datetime(2026, 9, 3, 12, 37),
            horizon_hours=0,
        )

def test_history_window_from_arbitrary_anchor():
    history_start, history_end = history_window(
        datetime(2026, 9, 3, 12, 37)
    )

    assert history_start == datetime(2026, 9, 3, 6, 40)
    assert history_end == datetime(2026, 9, 3, 12, 40)


def test_history_window_produces_exactly_72_buckets():
    history_start, history_end = history_window(
        datetime(2026, 9, 3, 12, 37)
    )

    timeline = aggregate_absorption_curves(
        curves=[],
        window_start=history_start,
        window_end=history_end,
        interval_minutes=5,
    )

    assert len(timeline) == 72


def test_history_and_forecast_windows_are_contiguous():
    anchor = datetime(2026, 9, 3, 12, 37)

    history_start, history_end = history_window(anchor)
    forecast_start, forecast_end = forecast_window(anchor)

    assert history_end == forecast_start
    assert history_start == datetime(2026, 9, 3, 6, 40)
    assert forecast_end == datetime(2026, 9, 3, 18, 40)


def test_history_and_forecast_produce_144_buckets():
    anchor = datetime(2026, 9, 3, 12, 37)

    history_start, history_end = history_window(anchor)
    forecast_start, forecast_end = forecast_window(anchor)

    history = aggregate_absorption_curves(
        curves=[],
        window_start=history_start,
        window_end=history_end,
        interval_minutes=5,
    )

    forecast = aggregate_absorption_curves(
        curves=[],
        window_start=forecast_start,
        window_end=forecast_end,
        interval_minutes=5,
    )

    assert len(history) == 72
    assert len(forecast) == 72
    assert len(history) + len(forecast) == 144


def test_history_window_rejects_invalid_history():
    with pytest.raises(ValueError):
        history_window(
            datetime(2026, 9, 3, 12, 37),
            history_hours=0,
        )