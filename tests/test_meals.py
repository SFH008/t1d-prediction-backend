from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from datetime import UTC, datetime

from app.api.meals import _to_utc_naive

from fastapi import HTTPException

import pytest
from pydantic import ValidationError

from unittest.mock import AsyncMock, MagicMock, patch

from app.api.calculations import calculate_meal_dose
from app.api.meals import (
    calculate_group_carbs,
    create_meal,
    update_meal_consumption,
)

from app.models import (
    CarbAbsorptionProfile,
    CarbGroupDefinition,
    Meal,
    MealCarbGroup,
    PatientCarbGroupSetting,
)

from app.schema.schemas import (
    MealConsumptionUpdate,
    MealCarbGroupResponse,
    MealCreate,
    MealResponse,
)

from sqlalchemy.exc import SQLAlchemyError

def test_to_utc_naive_converts_aware_datetime():
    value = datetime(
        2026,
        9,
        4,
        12,
        0,
        tzinfo=UTC,
    )

    result = _to_utc_naive(value)

    assert result == datetime(
        2026,
        9,
        4,
        12,
        0,
    )
    assert result.tzinfo is None


def test_to_utc_naive_preserves_naive_datetime():
    value = datetime(
        2026,
        9,
        4,
        12,
        0,
    )

    assert _to_utc_naive(value) == value

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

def test_meal_accepts_fat_and_protein_grams():
    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        meal_category="meal",
        carb_groups=[
            {
                "group_number": 10,
                "quantity_grams": 100,
            }
        ],
        fat_grams=Decimal("12.5"),
        protein_grams=Decimal("18.0"),
    )

    assert meal.fat_grams == Decimal("12.5")
    assert meal.protein_grams == Decimal("18.0")


def test_meal_defaults_fat_and_protein_to_zero():
    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        meal_category="meal",
        carb_groups=[
            {
                "group_number": 2,
                "quantity_grams": 40,
            }
        ],
    )

    assert meal.fat_grams == Decimal("0")
    assert meal.protein_grams == Decimal("0")


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("fat_grams", -0.1),
        ("protein_grams", -0.1),
    ],
)
def test_meal_rejects_negative_fat_or_protein(
    field_name,
    value,
):
    payload = {
        "meal_timestamp": datetime(2026, 9, 4, 12, 0),
        "meal_category": "meal",
        "carb_groups": [
            {
                "group_number": 2,
                "quantity_grams": 40,
            }
        ],
        field_name: value,
    }

    with pytest.raises(ValueError):
        MealCreate(**payload)

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
    def __init__(
        self,
        patient,
        definition,
        profile=None,
        patient_setting=None,
    ):
        self.patient = patient
        self.definition = definition
        self.profile = profile
        self.patient_setting = patient_setting
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
            return _ScalarResult(self.patient_setting)

        if self.execute_count == 5:
            return _ScalarResult(self.profile)

        if self.execute_count == 6:
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
        default_absorption_delay_minutes=25,
        is_active=True,
    )

    profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="slow",
        profile_name="Slow",
        duration_minutes=300,
        # The profile delay must no longer control component onset.
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
    assert component_absorption.absorption_delay_minutes == 25
    assert component_absorption.absorption_duration_minutes == 300
    assert component_absorption.curve_type == "linear"
    assert component_absorption.classification_source == "carb_group_default_v2"
    assert component_absorption.model_version == "deterministic_linear_v1"

    assert stored_group.group_number == 1
    assert stored_group.group_key == "pasta_cooked"
    assert stored_group.group_name == "Pasta, cooked"
    assert stored_group.carb_factor_g_per_g == Decimal("0.28")
    assert stored_group.quantity_grams == Decimal("100")
    assert stored_group.carbs_grams == Decimal("28.0")
    assert meal.total_carbs_grams == Decimal("28.0")


@pytest.mark.asyncio
async def test_create_meal_prefers_patient_carb_group_setting():
    patient_id = uuid4()

    patient = SimpleNamespace(id=patient_id)
    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=1,
        group_key="pasta_cooked",
        group_name="Pasta, cooked",
        carb_factor_g_per_g=Decimal("0.28"),
        default_absorption_profile_key="slow",
        default_absorption_delay_minutes=10,
        is_active=True,
    )
    patient_setting = PatientCarbGroupSetting(
        id=uuid4(),
        patient_id=patient_id,
        carb_group_definition_id=definition.id,
        absorption_profile_key="fast",
        absorption_delay_minutes=25,
        is_active=True,
    )
    profile = CarbAbsorptionProfile(
        id=uuid4(),
        patient_id=patient_id,
        profile_key="fast",
        profile_name="Fast",
        duration_minutes=60,
        absorption_delay_minutes=10,
        is_active=True,
    )
    session = _MealCreateSession(
        patient=patient,
        definition=definition,
        profile=profile,
        patient_setting=patient_setting,
    )
    meal_create = MealCreate(
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        meal_category="meal",
        carb_groups=[{"group_number": 1, "quantity_grams": 100}],
    )

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            AsyncMock(return_value=SimpleNamespace()),
        ),
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            AsyncMock(),
        ),
    ):
        await create_meal(
            patient_id=patient_id,
            meal_create=meal_create,
            db=session,
        )

    component_absorption = session.added[1]
    assert component_absorption.absorption_profile_key == "fast"
    assert component_absorption.absorption_delay_minutes == 25
    assert component_absorption.absorption_duration_minutes == 60
    assert (
        component_absorption.classification_source
        == "patient_carb_group_setting_v1"
    )


@pytest.mark.asyncio
async def test_create_meal_persists_fat_and_protein_grams():
    patient_id = uuid4()

    patient = SimpleNamespace(id=patient_id)

    definition = CarbGroupDefinition(
        id=uuid4(),
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        carb_factor_g_per_g=Decimal("0.06"),
        default_absorption_profile_key="slow",
        default_absorption_delay_minutes=10,
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
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        meal_category="meal",
        carb_groups=[
            {
                "group_number": 10,
                "quantity_grams": 100,
            }
        ],
        fat_grams=Decimal("12.5"),
        protein_grams=Decimal("18.0"),
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

    assert meal.fat_grams == Decimal("12.5")
    assert meal.protein_grams == Decimal("18.0")
    assert meal.total_carbs_grams == Decimal("6.0")
    assert session.commit_called is True

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
        default_absorption_delay_minutes=10,
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
        default_absorption_delay_minutes=10,
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
        default_absorption_delay_minutes=10,
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

def test_meal_response_exposes_fat_and_protein():
    response = MealResponse(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        meal_category="meal",
        status="captured",
        total_carbs_grams=6.0,
        fat_grams=12.5,
        protein_grams=18.0,
        source="manual",
        notes=None,
        created_at=datetime(2026, 9, 4, 12, 0),
        updated_at=datetime(2026, 9, 4, 12, 0),
        carb_groups=[],
    )

    assert response.fat_grams == 12.5
    assert response.protein_grams == 18.0

def test_consumption_accepts_actual_quantity():
    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 30,
            }
        ]
    )

    assert update.carb_groups[0].group_number == 10
    assert (
        update.carb_groups[0].consumed_quantity_grams
        == Decimal("30")
    )


def test_consumption_allows_zero_quantity():
    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 0,
            }
        ]
    )

    assert (
        update.carb_groups[0].consumed_quantity_grams
        == Decimal("0")
    )


def test_consumption_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        MealConsumptionUpdate(
            carb_groups=[
                {
                    "group_number": 10,
                    "consumed_quantity_grams": -0.1,
                }
            ]
        )


def test_consumption_rejects_client_supplied_consumed_carbs():
    with pytest.raises(ValidationError):
        MealConsumptionUpdate(
            carb_groups=[
                {
                    "group_number": 10,
                    "consumed_quantity_grams": 30,
                    "consumed_carbs_grams": 999,
                }
            ]
        )

def test_meal_group_consumption_initially_unknown():
    group = MealCarbGroup(
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=Decimal("50.0"),
        carb_factor_g_per_g=Decimal("0.06"),
        carbs_grams=Decimal("3.0"),
    )

    assert group.consumed_quantity_grams is None
    assert group.consumed_carbs_grams is None

def test_meal_group_response_allows_unknown_consumption():
    response = MealCarbGroupResponse(
        id=uuid4(),
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=50.0,
        carb_factor_g_per_g=0.06,
        carbs_grams=3.0,
        consumed_quantity_grams=None,
        consumed_carbs_grams=None,
        created_at=datetime(2026, 9, 4, 12, 0),
    )

    assert response.consumed_quantity_grams is None
    assert response.consumed_carbs_grams is None

@pytest.mark.asyncio
async def test_update_meal_consumption_derives_consumed_carbs():
    patient_id = uuid4()
    meal_id = uuid4()

    meal_group = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=Decimal("50.0"),
        carb_factor_g_per_g=Decimal("0.06"),
        carbs_grams=Decimal("3.0"),
    )

    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        carb_groups=[meal_group],
    )

    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 30,
            }
        ]
    )

    class _ConsumptionSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False
            self.flush_count = 0

        async def execute(self, stmt):
            return SimpleNamespace(
                scalar_one_or_none=lambda: meal
            )

        async def flush(self):
            self.flush_count += 1

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    session = _ConsumptionSession()

    with (
        patch(
            "app.api.meals.build_patient_absorption_timeline",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        patch(
            "app.api.meals.stage_patient_absorption_timeline",
            new=AsyncMock(),
        ),
        patch(
            "app.api.meals.complete_meal_recording_if_ready",
            new=AsyncMock(return_value=False),
        ) as complete_if_ready,
    ):
        updated = await update_meal_consumption(
            patient_id=patient_id,
            meal_id=meal_id,
            consumption_update=update,
            db=session,
        )

    group = updated.carb_groups[0]

    assert group.quantity_grams == Decimal("50.0")
    assert group.carbs_grams == Decimal("3.0")

    assert group.consumed_quantity_grams == Decimal("30")
    assert group.consumed_carbs_grams == Decimal("1.8")

    complete_if_ready.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        meal_id=meal_id,
    )

    assert session.commit_called is True
    assert session.flush_count == 1
    assert session.rollback_called is False

@pytest.mark.asyncio
async def test_update_meal_consumption_rebuilds_timeline_before_commit():
    patient_id = uuid4()
    meal_id = uuid4()

    meal_group = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=Decimal("50.0"),
        carb_factor_g_per_g=Decimal("0.06"),
        carbs_grams=Decimal("3.0"),
    )

    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        carb_groups=[meal_group],
    )

    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 30,
            }
        ]
    )

    class _ConsumptionSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False
            self.flush_count = 0

        async def execute(self, stmt):
            return SimpleNamespace(
                scalar_one_or_none=lambda: meal
            )

        async def flush(self):
            self.flush_count += 1

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    session = _ConsumptionSession()

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
        patch(
            "app.api.meals.complete_meal_recording_if_ready",
            new=AsyncMock(return_value=False),
        ) as complete_if_ready,
    ):
        await update_meal_consumption(
            patient_id=patient_id,
            meal_id=meal_id,
            consumption_update=update,
            db=session,
        )

    assert session.flush_count == 1

    build_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        anchor_timestamp=meal.meal_timestamp,
    )

    stage_timeline.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        timeline=built_timeline,
    )

    complete_if_ready.assert_awaited_once_with(
        db=session,
        patient_id=patient_id,
        meal_id=meal_id,
    )

    assert session.commit_called is True
    assert session.rollback_called is False

@pytest.mark.asyncio
async def test_update_meal_consumption_rejects_more_than_planned():
    patient_id = uuid4()
    meal_id = uuid4()

    meal_group = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=Decimal("50.0"),
        carb_factor_g_per_g=Decimal("0.06"),
        carbs_grams=Decimal("3.0"),
    )

    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
        carb_groups=[meal_group],
    )

    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 60,
            }
        ]
    )

    class _ConsumptionSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False

        async def execute(self, stmt):
            return SimpleNamespace(
                scalar_one_or_none=lambda: meal
            )

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    session = _ConsumptionSession()

    with pytest.raises(HTTPException) as exc:
        await update_meal_consumption(
            patient_id=patient_id,
            meal_id=meal_id,
            consumption_update=update,
            db=session,
        )

    assert exc.value.status_code == 400
    assert "cannot exceed planned quantity" in exc.value.detail

    assert meal_group.consumed_quantity_grams is None
    assert meal_group.consumed_carbs_grams is None
    assert session.commit_called is False
    assert session.rollback_called is True

@pytest.mark.asyncio
async def test_update_meal_consumption_is_atomic_across_components():
    patient_id = uuid4()
    meal_id = uuid4()

    fruit = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )

    bolognese = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=10,
        group_key="bolognese",
        group_name="Bolognese",
        quantity_grams=Decimal("50.0"),
        carb_factor_g_per_g=Decimal("0.06"),
        carbs_grams=Decimal("3.0"),
    )

    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
        carb_groups=[fruit, bolognese],
    )

    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 2,
                "consumed_quantity_grams": 20,
            },
            {
                "group_number": 10,
                "consumed_quantity_grams": 60,
            },
        ]
    )

    class _ConsumptionSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False

        async def execute(self, stmt):
            return SimpleNamespace(
                scalar_one_or_none=lambda: meal
            )

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    session = _ConsumptionSession()

    with pytest.raises(HTTPException):
        await update_meal_consumption(
            patient_id=patient_id,
            meal_id=meal_id,
            consumption_update=update,
            db=session,
        )

    assert fruit.consumed_quantity_grams is None
    assert fruit.consumed_carbs_grams is None

    assert bolognese.consumed_quantity_grams is None
    assert bolognese.consumed_carbs_grams is None

    assert session.commit_called is False
    assert session.rollback_called is True

def test_consumption_rejects_duplicate_group_numbers():
    with pytest.raises(ValueError):
        MealConsumptionUpdate(
            carb_groups=[
                {
                    "group_number": 2,
                    "consumed_quantity_grams": 20,
                },
                {
                    "group_number": 2,
                    "consumed_quantity_grams": 30,
                },
            ]
        )

@pytest.mark.asyncio
async def test_update_meal_consumption_rejects_group_not_in_meal():
    patient_id = uuid4()
    meal_id = uuid4()

    meal = Meal(
        id=meal_id,
        patient_id=patient_id,
        meal_timestamp=datetime.now(),
        meal_category="Lunch",
        total_carbs_grams=Decimal("40.0"),
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
    )

    fruit = MealCarbGroup(
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )

    meal.carb_groups = [fruit]

    db = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = meal
    db.execute.return_value = result

    payload = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 10,
                "consumed_quantity_grams": 20,
            }
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_meal_consumption(
            patient_id=patient_id,
            meal_id=meal_id,
            consumption_update=payload,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "is not part of this meal" in exc_info.value.detail

    assert fruit.consumed_quantity_grams is None
    assert fruit.consumed_carbs_grams is None

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()

@pytest.mark.asyncio
async def test_update_meal_consumption_persists_zero_consumption():
    patient_id = uuid4()
    meal_id = uuid4()

    meal = Meal(
        id=meal_id,
        patient_id=patient_id,
        meal_timestamp=datetime.now(),
        meal_category="Lunch",
        total_carbs_grams=Decimal("40.0"),
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
    )

    fruit = MealCarbGroup(
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )

    meal.carb_groups = [fruit]

    db = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = meal
    db.execute.return_value = result

    payload = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 2,
                "consumed_quantity_grams": 0,
            }
        ]
    )

    updated_meal = await update_meal_consumption(
        patient_id=patient_id,
        meal_id=meal_id,
        consumption_update=payload,
        db=db,
    )

    assert updated_meal is meal

    assert fruit.quantity_grams == Decimal("40.0")
    assert fruit.carbs_grams == Decimal("40.0")

    assert fruit.consumed_quantity_grams == Decimal("0")
    assert fruit.consumed_carbs_grams == Decimal("0.0")

    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()

@pytest.mark.asyncio
async def test_update_meal_consumption_rolls_back_when_timeline_rebuild_fails():
    patient_id = uuid4()
    meal_id = uuid4()

    meal_group = MealCarbGroup(
        id=uuid4(),
        meal_id=meal_id,
        group_number=2,
        group_key="fruit",
        group_name="Fruit",
        quantity_grams=Decimal("40.0"),
        carb_factor_g_per_g=Decimal("1.0"),
        carbs_grams=Decimal("40.0"),
    )

    meal = SimpleNamespace(
        id=meal_id,
        patient_id=patient_id,
        status="active",
        started_at=datetime(2026, 9, 8, 12, 5),
        meal_timestamp=datetime(2026, 9, 4, 12, 0),
        carb_groups=[meal_group],
    )

    update = MealConsumptionUpdate(
        carb_groups=[
            {
                "group_number": 2,
                "consumed_quantity_grams": 20,
            }
        ]
    )

    class _ConsumptionSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False
            self.flush_count = 0

        async def execute(self, stmt):
            return SimpleNamespace(
                scalar_one_or_none=lambda: meal
            )

        async def flush(self):
            self.flush_count += 1

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    session = _ConsumptionSession()

    with patch(
        "app.api.meals.build_patient_absorption_timeline",
        new=AsyncMock(
            side_effect=RuntimeError("timeline rebuild failed")
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="timeline rebuild failed",
        ):
            await update_meal_consumption(
                patient_id=patient_id,
                meal_id=meal_id,
                consumption_update=update,
                db=session,
            )

    assert session.flush_count == 1
    assert session.commit_called is False
    assert session.rollback_called is True