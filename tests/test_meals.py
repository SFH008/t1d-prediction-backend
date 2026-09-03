from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError


from app.api.calculations import calculate_meal_dose
from app.api.meals import calculate_group_carbs, create_meal
from app.models import CarbAbsorptionProfile, CarbGroupDefinition
from app.schema.schemas import MealCreate
from unittest.mock import AsyncMock, patch
from sqlalchemy.exc import SQLAlchemyError

def test_carb_factor_calculation():
    """
    100 g food × 0.30 g/g = 30 g carbohydrate.
    """
    result = calculate_group_carbs(100, 0.30)

    assert float(result) == 30.0


def test_carb_factor_calculation_preserves_fractional_carbs():
    """
    75 g food × 0.1333 g/g = 9.9975 g -> 10.0 g stored.
    """
    result = calculate_group_carbs(75, 0.1333)

    assert float(result) == 10.0


def test_meal_accepts_multiple_carb_groups():
    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 1, 12, 0),
        meal_category="lunch",
        carb_groups=[
            {
                "group_number": 1,
                "quantity_grams": 100,
            },
            {
                "group_number": 2,
                "quantity_grams": 50,
            },
        ],
    )

    assert len(meal.carb_groups) == 2


def test_meal_accepts_11_predefined_groups():
    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 1, 12, 0),
        meal_category="lunch",
        carb_groups=[
            {
                "group_number": number,
                "quantity_grams": 50,
            }
            for number in range(1, 12)
        ],
    )

    assert len(meal.carb_groups) == 11


def test_meal_rejects_more_than_12_groups():
    groups = [
        {
            "group_number": number,
            "group_key": f"carb_group_{number}",
            "group_name": f"Group {number}",
            "quantity_grams": 100,
            "carb_factor_g_per_g": 0.30,
        }
        for number in range(1, 14)
    ]

    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 1, 12, 0),
            meal_category="lunch",
            carb_groups=groups,
        )


def test_carb_group_number_must_be_1_to_12():
    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 1, 12, 0),
            meal_category="lunch",
            carb_groups=[
                {
                    "group_number": 13,
                    "quantity_grams": 100,
                }
            ],
        )

def test_meal_carb_group_rejects_client_supplied_factor():

    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 2, 12, 0),
            meal_category="medium",
            carb_groups=[
                {
                    "group_number": 1,
                    "quantity_grams": 100,
                    "carb_factor_g_per_g": 0.99,
                }
            ],
        )

def test_negative_quantity_is_rejected():
    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 1, 12, 0),
            meal_category="lunch",
            carb_groups=[
                {
                    "group_number": 1,
                    "quantity_grams": -1,
                }
            ],
        )

def test_meal_dose_calculation():
    result = calculate_meal_dose(
        carbohydrate_total_grams=75,
        carb_factor_g_per_unit=10,
        glucose_mg_dl=180,
        target_glucose_mg_dl=100,
        insulin_sensitivity_mg_dl_per_unit=40,
    )

    assert result.carbohydrate_dose_units == Decimal("7.50")
    assert result.correction_dose_units == Decimal("2.00")
    assert result.calculated_dose_units == Decimal("9.50")

def test_zero_food_quantity_is_rejected():
    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 1, 12, 0),
            meal_category="lunch",
            carb_groups=[
                {
                    "group_number": 1,
                    "quantity_grams": 0,
                }
            ],
        )

class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _MealCreateSession:
    def __init__(self, patient, definition, profile=None):
        self.patient = patient
        self.definition = definition
        self.profile = profile
        self.added = []
        self.commit_called = False
        self.rollback_called = False
        self.execute_count = 0
        self.flush_count = 0

    async def execute(self, stmt):
        self.execute_count += 1

        if self.execute_count == 1:
            return _ScalarResult(self.patient)

        if self.execute_count in (2, 3):
            return _ScalarResult(self.definition)

        if self.execute_count == 4:
            return _ScalarResult(self.profile)

        if self.execute_count == 5:
            return _ScalarResult(self.added[0])

        raise AssertionError(
            f"Unexpected execute call #{self.execute_count}"
        )

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1

        # The fake ORM needs identities before the component
        # absorption snapshot is created.
        meal = self.added[0]

        if meal.id is None:
            meal.id = uuid4()

        for group in meal.carb_groups:
            if group.id is None:
                group.id = uuid4()

    async def commit(self):
        self.commit_called = True

    async def rollback(self):
        self.rollback_called = True

@pytest.mark.asyncio
async def test_create_meal_uses_backend_carb_definition():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=1,
        group_key="pasta_cooked",
        group_name="Pasta, cooked",
        carb_factor_g_per_g=Decimal("0.28"),
        default_absorption_profile_key="slow",
        is_active=True,
    )

    profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="slow",
        profile_name="Slow",
        duration_minutes=300,
        absorption_delay_minutes=10,
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
        profile=profile,
    )

    meal_create = MealCreate(
        meal_timestamp=datetime(2026, 9, 2, 12, 0),
        meal_category="medium",
        carb_groups=[
            {
                "group_number": 1,
                "quantity_grams": 100,
            }
        ],
    )

    built_timeline = SimpleNamespace()

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            AsyncMock(return_value=built_timeline),
        ),
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            AsyncMock(),
        ),
    ):
        meal = await create_meal(
            patient_id=patient_id,
            meal_create=meal_create,
            db=session,
        )

    assert session.commit_called is True
    assert len(session.added) == 2

    stored_group = meal.carb_groups[0]

    component_absorption = session.added[1]

    assert component_absorption.meal_carb_group_id == stored_group.id
    assert component_absorption.patient_id == patient_id
    assert component_absorption.absorption_profile_id == profile.id
    assert component_absorption.absorption_profile_key == "slow"
    assert component_absorption.absorption_delay_minutes == 10
    assert component_absorption.absorption_duration_minutes == 300
    assert component_absorption.curve_type == "linear"
    assert component_absorption.classification_source == "carb_group_default_v1"
    assert component_absorption.model_version == "deterministic_linear_v1"

    assert stored_group.group_number == 1
    assert stored_group.group_key == "pasta_cooked"
    assert stored_group.group_name == "Pasta, cooked"
    assert stored_group.carb_factor_g_per_g == Decimal("0.28")
    assert stored_group.quantity_grams == Decimal("100")
    assert stored_group.carbs_grams == Decimal("28.0")
    assert meal.total_carbs_grams == Decimal("28.0")

@pytest.mark.asyncio
async def test_existing_meal_keeps_factor_snapshot_after_admin_change():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=1,
        group_key="pasta_cooked",
        group_name="Pasta, cooked",
        carb_factor_g_per_g=Decimal("0.28"),
        default_absorption_profile_key="slow",
        is_active=True,
    )

    profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="slow",
        profile_name="Slow",
        duration_minutes=300,
        absorption_delay_minutes=10,
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
        profile=profile,
    )

    meal_create = MealCreate(
        meal_timestamp=datetime(2026, 9, 2, 12, 0),
        meal_category="medium",
        carb_groups=[
            {
                "group_number": 1,
                "quantity_grams": 100,
            }
        ],
    )

    built_timeline = SimpleNamespace()

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            AsyncMock(return_value=built_timeline),
        ),
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            AsyncMock(),
        ),
    ):
        meal = await create_meal(
            patient_id=patient_id,
            meal_create=meal_create,
            db=session,
        )

    stored_group = meal.carb_groups[0]

    component_absorption = session.added[1]

    # Simulate later admin configuration changes.
    definition.carb_factor_g_per_g = Decimal("0.40")
    definition.default_absorption_profile_key = "fast"

    profile.absorption_delay_minutes = 5
    profile.duration_minutes = 60

    assert stored_group.carb_factor_g_per_g == Decimal("0.28")
    assert stored_group.carbs_grams == Decimal("28.0")
    assert meal.total_carbs_grams == Decimal("28.0")

    assert component_absorption.absorption_profile_key == "slow"
    assert component_absorption.absorption_delay_minutes == 10
    assert component_absorption.absorption_duration_minutes == 300
    assert component_absorption.absorption_profile_id == profile.id
    assert component_absorption.curve_type == "linear"
    assert component_absorption.model_version == "deterministic_linear_v1"

@pytest.mark.asyncio
async def test_create_meal_stages_absorption_timeline_before_single_commit():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=1,
        group_key="pasta_cooked",
        group_name="Pasta, cooked",
        carb_factor_g_per_g=Decimal("0.28"),
        default_absorption_profile_key="slow",
        is_active=True,
    )

    profile = SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="slow",
        absorption_delay_minutes=10,
        duration_minutes=300,
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
        profile=profile,
    )

    meal_create = MealCreate(
        meal_timestamp=datetime(
            2026, 9, 3, 12, 37
        ),
        meal_category="medium",
        carb_groups=[
            {
                "group_number": 1,
                "quantity_grams": 100,
            }
        ],
    )

    built_timeline = SimpleNamespace()

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            AsyncMock(return_value=built_timeline),
        ) as build_timeline,
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            AsyncMock(),
        ) as stage_timeline,
    ):
        await create_meal(
            patient_id=patient_id,
            meal_create=meal_create,
            db=session,
        )

    assert session.flush_count == 2

    build_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        anchor_timestamp=meal_create.meal_timestamp,
    )

    stage_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        timeline=built_timeline,
    )

    assert session.flush_count == 2

    build_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        anchor_timestamp=meal_create.meal_timestamp,
    )

    stage_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        timeline=built_timeline,
    )

    assert session.commit_called is True
    assert session.rollback_called is False

@pytest.mark.asyncio
async def test_create_meal_rolls_back_if_absorption_timeline_fails():
    patient_id = uuid4()

    patient = SimpleNamespace(
        id=patient_id,
    )

    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=1,
        group_key="pasta_cooked",
        group_name="Pasta, cooked",
        carb_factor_g_per_g=Decimal("0.28"),
        default_absorption_profile_key="slow",
        is_active=True,
    )

    profile = SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="slow",
        absorption_delay_minutes=10,
        duration_minutes=300,
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
        profile=profile,
    )

    meal_create = MealCreate(
        meal_timestamp=datetime(
            2026, 9, 3, 12, 37
        ),
        meal_category="medium",
        carb_groups=[
            {
                "group_number": 1,
                "quantity_grams": 100,
            }
        ],
    )

    with patch(
        "app.api.meals.build_patient_absorption_timeline",
        AsyncMock(
            side_effect=SQLAlchemyError(
                "forced timeline failure"
            )
        ),
    ):
        with pytest.raises(SQLAlchemyError):
            await create_meal(
                patient_id=patient_id,
                meal_create=meal_create,
                db=session,
            )

    assert session.flush_count == 2
    assert session.commit_called is False
    assert session.rollback_called is True