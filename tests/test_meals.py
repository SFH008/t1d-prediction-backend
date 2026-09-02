from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.calculations import calculate_meal_dose
from app.api.meals import calculate_group_carbs, create_meal
from app.models import CarbGroupDefinition
from app.schema.schemas import MealCreate

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
    def __init__(self, patient, definition):
        self.patient = patient
        self.definition = definition
        self.added = []
        self.commit_called = False
        self.execute_count = 0

    async def execute(self, stmt):
        self.execute_count += 1

        if self.execute_count == 1:
            return _ScalarResult(self.patient)

        if self.execute_count == 2:
            return _ScalarResult(self.definition)

        if self.execute_count == 3:
            return _ScalarResult(self.added[0])

        raise AssertionError(
            f"Unexpected execute call #{self.execute_count}"
        )

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_called = True


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
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
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

    meal = await create_meal(
        patient_id=patient_id,
        meal_create=meal_create,
        db=session,
    )

    assert session.commit_called is True
    assert len(session.added) == 1

    stored_group = meal.carb_groups[0]

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
        is_active=True,
    )

    session = _MealCreateSession(
        patient=patient,
        definition=definition,
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

    meal = await create_meal(
        patient_id=patient_id,
        meal_create=meal_create,
        db=session,
    )

    stored_group = meal.carb_groups[0]

    # Simulate a later system-admin configuration change.
    definition.carb_factor_g_per_g = Decimal("0.40")

    assert stored_group.carb_factor_g_per_g == Decimal("0.28")
    assert stored_group.carbs_grams == Decimal("28.0")
    assert meal.total_carbs_grams == Decimal("28.0")
