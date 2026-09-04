from dataclasses import dataclass

from app.services.meal_absorption import (
    resolve_meal_absorption_summary,
)


@dataclass(frozen=True)
class Component:
    absorption_profile_id: object
    absorption_profile_key: str
    absorption_delay_minutes: int
    absorption_duration_minutes: int


def component(
    key: str,
    *,
    delay: int = 10,
    duration: int,
):
    return Component(
        absorption_profile_id=None,
        absorption_profile_key=key,
        absorption_delay_minutes=delay,
        absorption_duration_minutes=duration,
    )


def test_single_fast_component_inherits_fast_profile():
    result = resolve_meal_absorption_summary([
        component("fast", duration=60),
    ])

    assert result.profile_key == "fast"
    assert result.delay_minutes == 10
    assert result.duration_minutes == 60
    assert result.classification_source == "component_single_v1"


def test_single_slow_component_inherits_slow_profile():
    result = resolve_meal_absorption_summary([
        component("slow", duration=300),
    ])

    assert result.profile_key == "slow"
    assert result.delay_minutes == 10
    assert result.duration_minutes == 300
    assert result.classification_source == "component_single_v1"


def test_same_profile_components_keep_profile():
    result = resolve_meal_absorption_summary([
        component("fast", duration=60),
        component("fast", duration=60),
    ])

    assert result.profile_key == "fast"
    assert result.delay_minutes == 10
    assert result.duration_minutes == 60
    assert result.classification_source == "component_uniform_v1"


def test_distinct_component_profiles_are_mixed_not_medium():
    result = resolve_meal_absorption_summary([
        component("fast", duration=60),
        component("slow", duration=300),
    ])

    assert result.profile_key == "mixed"
    assert result.delay_minutes == 10
    assert result.duration_minutes == 300
    assert result.classification_source == "component_mixed_v1"


def test_mixed_duration_covers_full_component_window():
    result = resolve_meal_absorption_summary([
        component("fast", delay=5, duration=60),
        component("slow", delay=20, duration=300),
    ])

    assert result.delay_minutes == 5

    # Aggregate summary spans first absorption start
    # through final component completion:
    # (20 + 300) - 5 = 315 minutes.
    assert result.duration_minutes == 315


def test_no_components_is_rejected():
    try:
        resolve_meal_absorption_summary([])
    except ValueError as exc:
        assert str(exc) == (
            "Meal requires at least one absorption component"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_single_component_summary_does_not_require_meal_category():
    result = resolve_meal_absorption_summary([
        component("fast", duration=60),
    ])

    assert result.profile_key == "fast"
    assert result.profile_id is None
    assert result.classification_source == "component_single_v1"


def test_mixed_summary_has_no_single_profile_id():
    result = resolve_meal_absorption_summary([
        component("fast", duration=60),
        component("slow", duration=300),
    ])

    assert result.profile_key == "mixed"
    assert result.profile_id is None
    assert result.classification_source == "component_mixed_v1"