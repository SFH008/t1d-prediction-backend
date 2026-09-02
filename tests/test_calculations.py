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

from app.api.calculations import (
    _round_down_to_increment,
    calculate_split_dose,
)


def test_round_down_to_increment_is_conservative():
    assert _round_down_to_increment(Decimal("1.58"), Decimal("0.05")) == Decimal("1.55")
    assert _round_down_to_increment(Decimal("1.58"), Decimal("0.10")) == Decimal("1.50")
    assert _round_down_to_increment(Decimal("1.78"), Decimal("0.50")) == Decimal("1.50")


def test_split_dose_uses_different_icr_at_dose_2_time():
    result = calculate_split_dose(
        carbohydrate_total_grams=80,
        fat_protein_addon_percent=0,
        dose_1_share_percent=60,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=8,
        insulin_rounding_increment_units=0.05,
        glucose_mg_dl=140,
        target_glucose_mg_dl=100,
        meal_isf_mg_dl_per_unit=40,
    )

    assert result.dose_1_carbohydrate_grams == Decimal("48")
    assert result.dose_2_carbohydrate_grams == Decimal("32")
    assert result.correction_dose_units == Decimal("1")
    assert result.dose_1_units == Decimal("5.80")
    assert result.dose_2_units == Decimal("4.00")
    assert result.total_planned_dose_units == Decimal("9.80")


def test_split_dose_correction_never_subtracts():
    result = calculate_split_dose(
        carbohydrate_total_grams=20,
        fat_protein_addon_percent=0,
        dose_1_share_percent=50,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=10,
        insulin_rounding_increment_units=0.05,
        glucose_mg_dl=80,
        target_glucose_mg_dl=100,
        meal_isf_mg_dl_per_unit=40,
    )

    assert result.correction_dose_units == Decimal("0")
    assert result.dose_1_units == Decimal("1.0")
    assert result.dose_2_units == Decimal("1.0")


def test_split_dose_applies_fat_protein_addon_before_split():
    result = calculate_split_dose(
        carbohydrate_total_grams=50,
        fat_protein_addon_percent=20,
        dose_1_share_percent=50,
        meal_icr_g_per_unit=10,
        dose_2_icr_g_per_unit=10,
        insulin_rounding_increment_units=0.05,
    )

    assert result.fat_protein_addon_grams == Decimal("10")
    assert result.effective_carbohydrate_grams == Decimal("60")
    assert result.dose_1_carbohydrate_grams == Decimal("30")
    assert result.dose_2_carbohydrate_grams == Decimal("30")
