"""
Meal capture endpoints.

The meal is the primary user interaction for carbohydrate capture.
Individual carbohydrate groups are submitted as children of the meal.

Step 1 lifecycle:
    meal -> captured

Later steps will extend the meal lifecycle without changing the meal ID.
"""

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    CarbAbsorptionProfile,
    CarbGroupDefinition,
    Meal,
    MealCarbGroup,
    MealComponentAbsorption,
    Patient,
)
from app.schema.schemas import (
    MealCreate,
    MealResponse,
)


router = APIRouter(tags=["Meals"])

MAX_CARB_GROUPS = 12
CUSTOM_GROUP_NUMBER = 12


def calculate_group_carbs(quantity_grams: float, carb_factor_g_per_g: float) -> Decimal:
    """
    Calculate carbohydrate contribution from one group.

    Result is rounded to one decimal place because meal carb totals are
    stored at 0.1 g precision.
    """
    result = (
        Decimal(str(quantity_grams))
        * Decimal(str(carb_factor_g_per_g))
    )
    return result.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@router.post(
    "/patients/{patient_id}/meals",
    response_model=MealResponse,
    status_code=201,
)
async def create_meal(
    patient_id: UUID,
    meal_create: MealCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Capture a meal and all of its carbohydrate groups atomically.

    The server calculates and stores each group's carbohydrate contribution
    and the meal total. The client must not be trusted to provide totals.
    """

    patient_stmt = select(Patient).where(Patient.id == patient_id)
    patient_result = await db.execute(patient_stmt)
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found",
        )

    if len(meal_create.carb_groups) > MAX_CARB_GROUPS:
        raise HTTPException(
            status_code=400,
            detail="A meal may contain at most 12 carbohydrate groups",
        )

    group_numbers = [group.group_number for group in meal_create.carb_groups]
    if len(group_numbers) != len(set(group_numbers)):
        raise HTTPException(
            status_code=400,
            detail="Carbohydrate group numbers must be unique",
        )

    # Group 12 is reserved for the future custom-group implementation.
    for group in meal_create.carb_groups:
        if group.group_number == CUSTOM_GROUP_NUMBER:
            raise HTTPException(
                status_code=400,
                detail="Carbohydrate group 12 (Custom) is reserved for a future implementation",
            )

    meal = Meal(
        patient_id=patient_id,
        meal_timestamp=meal_create.meal_timestamp,
        meal_category=meal_create.meal_category,
        status="captured",
        source=meal_create.source or "manual",
        notes=meal_create.notes,
        total_carbs_grams=Decimal("0.0"),
    )

    total_carbs = Decimal("0.0")

    for group in meal_create.carb_groups:
        definition_stmt = select(
            CarbGroupDefinition
        ).where(
            CarbGroupDefinition.group_number
            == group.group_number,
            CarbGroupDefinition.is_active.is_(True),
        )

        definition_result = await db.execute(
            definition_stmt
        )

        definition = (
            definition_result.scalar_one_or_none()
        )

        if definition is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No active carbohydrate definition "
                    f"exists for group {group.group_number}"
                ),
            )

        carbs_grams = calculate_group_carbs(
            group.quantity_grams,
            definition.carb_factor_g_per_g,
        )

        meal_group = MealCarbGroup(
            group_number=definition.group_number,
            group_key=definition.group_key,
            group_name=definition.group_name,
            quantity_grams=Decimal(
                str(group.quantity_grams)
            ),
            carb_factor_g_per_g=Decimal(
                str(definition.carb_factor_g_per_g)
            ),
            carbs_grams=carbs_grams,
        )

        meal.carb_groups.append(meal_group)
        total_carbs += carbs_grams

    meal.total_carbs_grams = total_carbs.quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )

    db.add(meal)

    # Allocate database identities without committing. This allows each
    # component absorption snapshot to reference its MealCarbGroup while
    # keeping the complete meal capture atomic.
    await db.flush()

    for meal_group in meal.carb_groups:
        definition_stmt = select(
            CarbGroupDefinition
        ).where(
            CarbGroupDefinition.group_number == meal_group.group_number,
            CarbGroupDefinition.is_active.is_(True),
        )

        definition_result = await db.execute(definition_stmt)
        definition = definition_result.scalar_one_or_none()

        if definition is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No active carbohydrate definition "
                    f"exists for group {meal_group.group_number}"
                ),
            )

        profile_key = definition.default_absorption_profile_key

        if profile_key is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No default absorption profile is configured "
                    f"for carbohydrate group {meal_group.group_number}"
                ),
            )

        profile_stmt = select(
            CarbAbsorptionProfile
        ).where(
            CarbAbsorptionProfile.patient_id == patient_id,
            CarbAbsorptionProfile.profile_key == profile_key,
            CarbAbsorptionProfile.is_active.is_(True),
        )

        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

        if profile is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No active '{profile_key}' carbohydrate absorption "
                    "profile exists for this patient"
                ),
            )

        component_absorption = MealComponentAbsorption(
            meal_carb_group_id=meal_group.id,
            patient_id=patient_id,
            absorption_profile_id=profile.id,
            absorption_profile_key=profile.profile_key,
            absorption_delay_minutes=profile.absorption_delay_minutes,
            absorption_duration_minutes=profile.duration_minutes,
            curve_type="linear",
            curve_parameters=None,
            classification_source="carb_group_default_v1",
            model_version="deterministic_linear_v1",
        )

        db.add(component_absorption)

    await db.commit()

    # Reload children explicitly because the relationship is async-session
    # safe and the response needs the complete aggregate.
    stmt = (
        select(Meal)
        .options(selectinload(Meal.carb_groups))
        .where(Meal.id == meal.id)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get(
    "/patients/{patient_id}/meals",
    response_model=list[MealResponse],
)
async def get_meals(
    patient_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return captured meals for a patient, newest first."""

    patient_stmt = select(Patient).where(Patient.id == patient_id)
    patient_result = await db.execute(patient_stmt)
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found",
        )

    stmt = (
        select(Meal)
        .options(selectinload(Meal.carb_groups))
        .where(Meal.patient_id == patient_id)
        .order_by(Meal.meal_timestamp.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    return result.scalars().all()
