from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MealAbsorptionSummary:
    profile_key: str
    profile_id: object | None
    delay_minutes: int
    duration_minutes: int
    classification_source: str


def resolve_meal_absorption_summary(
    components: Iterable[object],
) -> MealAbsorptionSummary:
    items = list(components)

    if not items:
        raise ValueError(
            "Meal requires at least one absorption component"
        )

    first_start = min(
        item.absorption_delay_minutes
        for item in items
    )

    last_end = max(
        item.absorption_delay_minutes
        + item.absorption_duration_minutes
        for item in items
    )

    profile_keys = {
        item.absorption_profile_key
        for item in items
    }

    if len(items) == 1:
        item = items[0]

        return MealAbsorptionSummary(
            profile_key=item.absorption_profile_key,
            profile_id=item.absorption_profile_id,
            delay_minutes=item.absorption_delay_minutes,
            duration_minutes=item.absorption_duration_minutes,
            classification_source="component_single_v1",
        )

    if len(profile_keys) == 1:
        item = items[0]

        return MealAbsorptionSummary(
            profile_key=item.absorption_profile_key,
            profile_id=item.absorption_profile_id,
            delay_minutes=first_start,
            duration_minutes=last_end - first_start,
            classification_source="component_uniform_v1",
        )

    return MealAbsorptionSummary(
        profile_key="mixed",
        profile_id=None,
        delay_minutes=first_start,
        duration_minutes=last_end - first_start,
        classification_source="component_mixed_v1",
    )