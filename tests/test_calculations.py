"""
Tests for the Meal -> Calculation transition.
"""

from decimal import Decimal

from app.api.calculations import _round_units


def test_round_units():
    assert _round_units(Decimal("1.234")) == Decimal("1.23")
    assert _round_units(Decimal("1.235")) == Decimal("1.24")


def test_carb_factor_calculation():
    carbohydrate_total = Decimal("60")
    carb_factor = Decimal("10")

    dose = _round_units(
        carbohydrate_total / carb_factor
    )

    assert dose == Decimal("6.00")


def test_carb_factor_changes_calculated_dose():
    carbohydrate_total = Decimal("60")

    breakfast_factor = Decimal("8")
    dinner_factor = Decimal("12")

    breakfast_dose = _round_units(
        carbohydrate_total / breakfast_factor
    )
    dinner_dose = _round_units(
        carbohydrate_total / dinner_factor
    )

    assert breakfast_dose == Decimal("7.50")
    assert dinner_dose == Decimal("5.00")
    assert breakfast_dose != dinner_dose


def test_negative_correction_is_zero():
    glucose = Decimal("100")
    target = Decimal("120")
    isf = Decimal("40")

    correction = _round_units(
        (glucose - target) / isf
    )

    correction = max(correction, Decimal("0"))

    assert correction == Decimal("0.00")
