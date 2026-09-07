"""
Persistence-contract tests for the B2.3 Warsaw-inspired fat/protein model.

These tests deliberately keep the new fat/protein model separate from the
legacy calculation-version-3 fat_protein_addon_* fields.
"""

from decimal import Decimal

from app.models import DoseStrategySettings, MealCalculation


def test_dose_strategy_has_conservative_fat_protein_defaults():
    mode_column = DoseStrategySettings.__table__.c.fat_protein_mode
    scaling_column = (
        DoseStrategySettings.__table__.c.fat_protein_scaling_percent
    )

    assert mode_column.default.arg == "disabled"
    assert scaling_column.default.arg == Decimal("0")

def test_dose_strategy_preserves_legacy_fat_protein_addon_field():
    settings = DoseStrategySettings(
        fat_protein_addon_percent=Decimal("20"),
    )

    assert settings.fat_protein_addon_percent == Decimal("20")


def test_meal_calculation_can_snapshot_fat_protein_model():
    calculation = MealCalculation(
        carbohydrate_total_grams=Decimal("50.0"),
        calculation_version="3",
        fat_protein_model_mode="advisory",
        fat_protein_model_scaling_percent=Decimal("50"),
        fat_protein_fat_grams=Decimal("10.0"),
        fat_protein_protein_grams=Decimal("20.0"),
        fat_protein_fat_kcal=Decimal("90"),
        fat_protein_protein_kcal=Decimal("80"),
        fat_protein_total_kcal=Decimal("170"),
        fat_protein_units=Decimal("1.7"),
        fat_protein_theoretical_carb_equivalent_grams=Decimal("17"),
        fat_protein_scaled_carb_equivalent_grams=Decimal("8.5"),
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        fat_protein_model_version="warsaw_v1",
    )

    assert calculation.fat_protein_model_mode == "advisory"
    assert calculation.fat_protein_model_scaling_percent == Decimal("50")

    assert calculation.fat_protein_fat_grams == Decimal("10.0")
    assert calculation.fat_protein_protein_grams == Decimal("20.0")

    assert calculation.fat_protein_fat_kcal == Decimal("90")
    assert calculation.fat_protein_protein_kcal == Decimal("80")
    assert calculation.fat_protein_total_kcal == Decimal("170")

    assert calculation.fat_protein_units == Decimal("1.7")
    assert (
        calculation.fat_protein_theoretical_carb_equivalent_grams
        == Decimal("17")
    )
    assert (
        calculation.fat_protein_scaled_carb_equivalent_grams
        == Decimal("8.5")
    )
    assert (
        calculation.fat_protein_effective_carb_equivalent_grams
        == Decimal("0")
    )

    assert calculation.fat_protein_model_version == "warsaw_v1"


def test_new_fat_protein_snapshot_does_not_replace_legacy_fields():
    calculation = MealCalculation(
        carbohydrate_total_grams=Decimal("50.0"),
        calculation_version="3",
        fat_protein_addon_percent=Decimal("20"),
        fat_protein_addon_grams=Decimal("10"),
        effective_carbohydrate_grams=Decimal("60"),
        fat_protein_model_mode="disabled",
        fat_protein_model_scaling_percent=Decimal("0"),
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        fat_protein_model_version="warsaw_v1",
    )

    # Historical v3 semantics remain independently readable.
    assert calculation.fat_protein_addon_percent == Decimal("20")
    assert calculation.fat_protein_addon_grams == Decimal("10")
    assert calculation.effective_carbohydrate_grams == Decimal("60")

    # B2.3 Warsaw semantics are a separate snapshot.
    assert calculation.fat_protein_model_mode == "disabled"
    assert calculation.fat_protein_model_scaling_percent == Decimal("0")
    assert (
        calculation.fat_protein_effective_carb_equivalent_grams
        == Decimal("0")
    )
