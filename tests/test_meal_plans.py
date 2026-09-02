from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from app.api.meal_plans import _build_meal_plan_response
from app.models import Meal, MealCalculation, MealDoseEvent


def _meal():
    return Meal(
        id=uuid4(),
        patient_id=uuid4(),
        meal_timestamp=datetime(2026, 9, 2, 10, 40),
        meal_category="test",
        total_carbs_grams=Decimal("10.0"),
        absorption_profile_key="medium",
        absorption_classification_source="meal_category_rule_v1",
    )


def _calculation(meal):
    return MealCalculation(
        id=uuid4(),
        meal_id=meal.id,
        patient_id=meal.patient_id,
        calculated_at=datetime(2026, 9, 2, 11, 56),
        glucose_mg_dl=Decimal("120"),
        target_glucose_mg_dl=Decimal("100"),
        carb_factor_g_per_unit=Decimal("16"),
        insulin_sensitivity_mg_dl_per_unit=Decimal("150"),
        carbohydrate_total_grams=Decimal("10"),
        meal_basal_drift_mg_dl_per_hour=Decimal("0"),
        absorption_profile_key="medium",
        absorption_duration_minutes=150,
        absorption_delay_minutes=10,
        absorption_classification_source="meal_category_rule_v1",
        dose_1_share_percent=Decimal("60"),
        dose_2_share_percent=Decimal("40"),
        dose_2_delay_minutes=75,
        dose_2_timestamp=datetime(2026, 9, 2, 11, 55),
        dose_2_carb_factor_g_per_unit=Decimal("12"),
        dose_2_insulin_sensitivity_mg_dl_per_unit=Decimal("120"),
        dose_2_basal_drift_mg_dl_per_hour=Decimal("0"),
        dose_1_units=Decimal("0.500"),
        dose_2_units=Decimal("0.300"),
        total_planned_dose_units=Decimal("0.800"),
        strategy_source="integration_test",
        strategy_version="v3-test-1",
        calculation_version="3",
    )


def _events(meal, calculation):
    return [
        MealDoseEvent(
            id=uuid4(),
            patient_id=meal.patient_id,
            meal_id=meal.id,
            calculation_id=calculation.id,
            dose_number=2,
            planned_timestamp=datetime(2026, 9, 2, 11, 55),
            planned_units=Decimal("0.300"),
            status="planned",
            created_at=datetime(2026, 9, 2, 11, 56),
            updated_at=datetime(2026, 9, 2, 11, 56),
        ),
        MealDoseEvent(
            id=uuid4(),
            patient_id=meal.patient_id,
            meal_id=meal.id,
            calculation_id=calculation.id,
            dose_number=1,
            planned_timestamp=datetime(2026, 9, 2, 10, 40),
            planned_units=Decimal("0.500"),
            actual_timestamp=datetime(2026, 9, 2, 10, 40),
            actual_units=Decimal("0.500"),
            status="given",
            created_at=datetime(2026, 9, 2, 11, 56),
            updated_at=datetime(2026, 9, 2, 12, 7),
        ),
    ]


def test_meal_plan_response_consolidates_frontend_fields():
    meal = _meal()
    calculation = _calculation(meal)

    response = _build_meal_plan_response(
        meal=meal,
        calculation=calculation,
        dose_events=_events(meal, calculation),
    )

    assert response.meal.total_carbs_grams == 10.0
    assert response.absorption.profile_key == "medium"
    assert response.absorption.duration_minutes == 150
    assert response.calculation.meal_icr_g_per_unit == 16.0
    assert response.calculation.dose_2_icr_g_per_unit == 12.0
    assert response.calculation.total_planned_dose_units == 0.8


def test_meal_plan_sorts_dose_events_for_frontend():
    meal = _meal()
    calculation = _calculation(meal)

    response = _build_meal_plan_response(
        meal=meal,
        calculation=calculation,
        dose_events=_events(meal, calculation),
    )

    assert [event.dose_number for event in response.dose_events] == [1, 2]
    assert response.dose_events[0].status == "given"
    assert response.dose_events[1].status == "planned"


def test_historical_plan_preserves_planned_and_actual_values():
    meal = _meal()
    calculation = _calculation(meal)
    events = _events(meal, calculation)
    events[0].status = "adjusted"
    events[0].actual_units = Decimal("0.200")
    events[0].actual_timestamp = datetime(2026, 9, 2, 11, 55)

    response = _build_meal_plan_response(
        meal=meal,
        calculation=calculation,
        dose_events=events,
    )

    dose2 = response.dose_events[1]
    assert dose2.planned_units == 0.3
    assert dose2.actual_units == 0.2
    assert dose2.status == "adjusted"
