from decimal import Decimal

import pytest

from app.services.fat_protein_model import (
    FAT_PROTEIN_MODE_ADVISORY,
    FAT_PROTEIN_MODE_DISABLED,
    calculate_fat_protein_model,
)


def test_zero_fat_and_protein_produces_zero_model_values():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("0"),
        protein_grams=Decimal("0"),
        mode=FAT_PROTEIN_MODE_DISABLED,
        scaling_percent=Decimal("0"),
    )

    assert result.fat_kcal == Decimal("0")
    assert result.protein_kcal == Decimal("0")
    assert result.total_fat_protein_kcal == Decimal("0")
    assert result.fat_protein_units == Decimal("0")
    assert result.theoretical_carb_equivalent_grams == Decimal("0")
    assert result.scaled_carb_equivalent_grams == Decimal("0")
    assert result.effective_carb_equivalent_grams == Decimal("0")


def test_fat_and_protein_are_converted_to_energy_separately():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_DISABLED,
        scaling_percent=Decimal("0"),
    )

    assert result.fat_kcal == Decimal("90")
    assert result.protein_kcal == Decimal("80")
    assert result.total_fat_protein_kcal == Decimal("170")


def test_fpu_is_total_fat_protein_kcal_divided_by_100():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_DISABLED,
        scaling_percent=Decimal("0"),
    )

    assert result.fat_protein_units == Decimal("1.7")


def test_theoretical_carb_equivalent_is_total_kcal_divided_by_10():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_DISABLED,
        scaling_percent=Decimal("0"),
    )

    assert result.theoretical_carb_equivalent_grams == Decimal("17")


def test_scaling_percent_applies_to_theoretical_carb_equivalent():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_ADVISORY,
        scaling_percent=Decimal("50"),
    )

    assert result.theoretical_carb_equivalent_grams == Decimal("17")
    assert result.scaled_carb_equivalent_grams == Decimal("8.5")


def test_disabled_mode_forces_effective_contribution_to_zero():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_DISABLED,
        scaling_percent=Decimal("100"),
    )

    assert result.theoretical_carb_equivalent_grams == Decimal("17")
    assert result.scaled_carb_equivalent_grams == Decimal("17")
    assert result.effective_carb_equivalent_grams == Decimal("0")


def test_advisory_mode_keeps_effective_contribution_zero():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_ADVISORY,
        scaling_percent=Decimal("100"),
    )

    assert result.theoretical_carb_equivalent_grams == Decimal("17")
    assert result.scaled_carb_equivalent_grams == Decimal("17")
    assert result.effective_carb_equivalent_grams == Decimal("0")


def test_zero_scaling_forces_zero_scaled_contribution():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode=FAT_PROTEIN_MODE_ADVISORY,
        scaling_percent=Decimal("0"),
    )

    assert result.scaled_carb_equivalent_grams == Decimal("0")
    assert result.effective_carb_equivalent_grams == Decimal("0")


def test_negative_fat_is_rejected():
    with pytest.raises(ValueError, match="Fat grams cannot be negative"):
        calculate_fat_protein_model(
            fat_grams=Decimal("-1"),
            protein_grams=Decimal("20"),
            mode=FAT_PROTEIN_MODE_DISABLED,
            scaling_percent=Decimal("0"),
        )


def test_negative_protein_is_rejected():
    with pytest.raises(ValueError, match="Protein grams cannot be negative"):
        calculate_fat_protein_model(
            fat_grams=Decimal("10"),
            protein_grams=Decimal("-1"),
            mode=FAT_PROTEIN_MODE_DISABLED,
            scaling_percent=Decimal("0"),
        )


def test_negative_scaling_percent_is_rejected():
    with pytest.raises(
        ValueError,
        match="Fat/protein scaling percent cannot be negative",
    ):
        calculate_fat_protein_model(
            fat_grams=Decimal("10"),
            protein_grams=Decimal("20"),
            mode=FAT_PROTEIN_MODE_DISABLED,
            scaling_percent=Decimal("-1"),
        )


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="Unsupported fat/protein mode"):
        calculate_fat_protein_model(
            fat_grams=Decimal("10"),
            protein_grams=Decimal("20"),
            mode="unknown",
            scaling_percent=Decimal("0"),
        )

def test_enabled_mode_uses_scaled_contribution():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode="enabled",
        scaling_percent=Decimal("50"),
    )

    assert result.theoretical_carb_equivalent_grams == Decimal("17")
    assert result.scaled_carb_equivalent_grams == Decimal("8.5")
    assert result.effective_carb_equivalent_grams == Decimal("8.5")


def test_enabled_mode_with_zero_scaling_still_has_zero_effective_contribution():
    result = calculate_fat_protein_model(
        fat_grams=Decimal("10"),
        protein_grams=Decimal("20"),
        mode="enabled",
        scaling_percent=Decimal("0"),
    )

    assert result.scaled_carb_equivalent_grams == Decimal("0")
    assert result.effective_carb_equivalent_grams == Decimal("0")


def test_scaling_percent_above_100_is_rejected():
    with pytest.raises(
        ValueError,
        match="Fat/protein scaling percent cannot exceed 100",
    ):
        calculate_fat_protein_model(
            fat_grams=Decimal("10"),
            protein_grams=Decimal("20"),
            mode=FAT_PROTEIN_MODE_ADVISORY,
            scaling_percent=Decimal("101"),
        )