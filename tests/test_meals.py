from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.meals import calculate_group_carbs
from app.api.calculations import calculate_meal_dose
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
                "group_key": "carb_group_1",
                "group_name": "Predefined group 1",
                "quantity_grams": 100,
                "carb_factor_g_per_g": 0.30,
            },
            {
                "group_number": 2,
                "group_key": "carb_group_2",
                "group_name": "Predefined group 2",
                "quantity_grams": 50,
                "carb_factor_g_per_g": 0.50,
            },
        ],
    )

    assert len(meal.carb_groups) == 2


def test_meal_accepts_at_most_12_groups():
    groups = [
        {
            "group_number": number,
            "group_key": f"carb_group_{number}",
            "group_name": f"Predefined group {number}",
            "quantity_grams": 100,
            "carb_factor_g_per_g": 0.30,
        }
        for number in range(1, 13)
    ]

    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 1, 12, 0),
        meal_category="lunch",
        carb_groups=groups,
    )

    assert len(meal.carb_groups) == 12


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
                    "group_key": "invalid",
                    "group_name": "Invalid",
                    "quantity_grams": 100,
                    "carb_factor_g_per_g": 0.30,
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
                    "group_key": "carb_group_1",
                    "group_name": "Group 1",
                    "quantity_grams": -1,
                    "carb_factor_g_per_g": 0.30,
                }
            ],
        )


def test_negative_carb_factor_is_rejected():
    with pytest.raises(ValidationError):
        MealCreate(
            meal_timestamp=datetime(2026, 9, 1, 12, 0),
            meal_category="lunch",
            carb_groups=[
                {
                    "group_number": 1,
                    "group_key": "carb_group_1",
                    "group_name": "Group 1",
                    "quantity_grams": 100,
                    "carb_factor_g_per_g": -0.1,
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

def test_zero_carb_factor_is_valid():
    meal = MealCreate(
        meal_timestamp=datetime(2026, 9, 1, 12, 0),
        meal_category="lunch",
        carb_groups=[
            {
                "group_number": 1,
                "group_key": "carb_group_1",
                "group_name": "Group 1",
                "quantity_grams": 100,
                "carb_factor_g_per_g": 0,
            }
        ],
    )

    assert meal.carb_groups[0].carb_factor_g_per_g == 0
