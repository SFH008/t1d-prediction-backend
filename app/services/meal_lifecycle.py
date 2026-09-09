"""
Backend-owned meal lifecycle transitions.

Meal lifecycle state is durable server state. Clients may request transitions,
but they must not infer or manufacture lifecycle state locally.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Meal, MealDoseEvent


class MealLifecycleError(ValueError):
    """Raised when a requested meal lifecycle transition is invalid."""


def start_meal(
    meal: Meal,
    *,
    started_at: datetime,
) -> Meal:
    """
    Transition a captured meal to active.

    meal_timestamp remains the planning/capture timestamp.
    started_at records the actual lifecycle start.
    """

    if meal.status != "captured":
        raise MealLifecycleError(
            f"Meal cannot be started from status {meal.status!r}"
        )

    if meal.started_at is not None:
        raise MealLifecycleError(
            "Meal already has a started_at timestamp"
        )

    meal.status = "active"
    meal.started_at = started_at

    return meal


_MEAL_COMPLETION_DOSE_STATUSES = frozenset({
    "given",
    "adjusted",
    "skipped",
})


def is_meal_recording_complete(
    meal: Meal,
    *,
    dose_events,
) -> bool:
    """
    Return whether an active meal's human recording workflow is complete.

    Completion means:
    - every carbohydrate component has known actual consumption; and
    - every planned dose event has been resolved as given, adjusted, or skipped.

    Explicit zero consumption is known consumption.

    This lifecycle state does not mean physiological activity has ended.
    Completed meals may continue contributing COB, IOB, delayed nutrient
    effects, and forecasting state.
    """

    if meal.status != "active":
        return False

    if not meal.carb_groups:
        return False

    if any(
        group.consumed_quantity_grams is None
        for group in meal.carb_groups
    ):
        return False

    dose_events = list(dose_events)

    if not dose_events:
        return False

    return all(
        event.status in _MEAL_COMPLETION_DOSE_STATUSES
        for event in dose_events
    )


def complete_meal_if_recorded(
    meal: Meal,
    *,
    dose_events,
) -> bool:
    """
    Transition active -> completed when actual meal recording is complete.

    Returns True only when this call performs the transition.
    """

    if not is_meal_recording_complete(
        meal,
        dose_events=dose_events,
    ):
        return False

    meal.status = "completed"
    return True



async def complete_meal_recording_if_ready(
    *,
    db: AsyncSession,
    patient_id,
    meal_id,
) -> bool:
    """
    Load authoritative persisted recording state and complete the meal
    when the Actual Meal workflow is fully resolved.

    The caller must flush pending consumption/dose changes first.
    This function never commits; completion remains part of the caller's
    existing transaction.
    """

    meal_result = await db.execute(
        select(Meal)
        .options(selectinload(Meal.carb_groups))
        .where(
            Meal.id == meal_id,
            Meal.patient_id == patient_id,
        )
    )
    meal = meal_result.scalar_one_or_none()

    if meal is None:
        return False

    dose_result = await db.execute(
        select(MealDoseEvent).where(
            MealDoseEvent.meal_id == meal_id,
            MealDoseEvent.patient_id == patient_id,
        )
    )
    dose_events = dose_result.scalars().all()

    return complete_meal_if_recorded(
        meal,
        dose_events=dose_events,
    )
