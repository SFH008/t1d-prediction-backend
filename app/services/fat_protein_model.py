from dataclasses import dataclass
from decimal import Decimal


FAT_PROTEIN_MODEL_VERSION = "warsaw_v1"

FAT_PROTEIN_MODE_DISABLED = "disabled"
FAT_PROTEIN_MODE_ADVISORY = "advisory"
FAT_PROTEIN_MODE_ENABLED = "enabled"

_SUPPORTED_MODES = {
    FAT_PROTEIN_MODE_DISABLED,
    FAT_PROTEIN_MODE_ADVISORY,
    FAT_PROTEIN_MODE_ENABLED,
}


@dataclass(frozen=True)
class FatProteinModelResult:
    fat_grams: Decimal
    protein_grams: Decimal

    fat_kcal: Decimal
    protein_kcal: Decimal
    total_fat_protein_kcal: Decimal

    fat_protein_units: Decimal
    theoretical_carb_equivalent_grams: Decimal

    scaling_percent: Decimal
    scaled_carb_equivalent_grams: Decimal

    mode: str
    effective_carb_equivalent_grams: Decimal


def calculate_fat_protein_model(
    *,
    fat_grams,
    protein_grams,
    mode,
    scaling_percent,
) -> FatProteinModelResult:
    fat = Decimal(str(fat_grams))
    protein = Decimal(str(protein_grams))
    scaling = Decimal(str(scaling_percent))

    if fat < 0:
        raise ValueError("Fat grams cannot be negative")

    if protein < 0:
        raise ValueError("Protein grams cannot be negative")

    if scaling < 0:
        raise ValueError("Fat/protein scaling percent cannot be negative")

    if scaling > 100:
        raise ValueError("Fat/protein scaling percent cannot exceed 100")

    if mode not in _SUPPORTED_MODES:
        raise ValueError(f"Unsupported fat/protein mode: {mode}")

    fat_kcal = fat * Decimal("9")
    protein_kcal = protein * Decimal("4")
    total_kcal = fat_kcal + protein_kcal

    fat_protein_units = total_kcal / Decimal("100")
    theoretical_carb_equivalent = total_kcal / Decimal("10")

    scaled_carb_equivalent = (
        theoretical_carb_equivalent
        * scaling
        / Decimal("100")
    )

    if mode == FAT_PROTEIN_MODE_ENABLED:
        effective_carb_equivalent = scaled_carb_equivalent
    else:
        effective_carb_equivalent = Decimal("0")

    return FatProteinModelResult(
        fat_grams=fat,
        protein_grams=protein,
        fat_kcal=fat_kcal,
        protein_kcal=protein_kcal,
        total_fat_protein_kcal=total_kcal,
        fat_protein_units=fat_protein_units,
        theoretical_carb_equivalent_grams=theoretical_carb_equivalent,
        scaling_percent=scaling,
        scaled_carb_equivalent_grams=scaled_carb_equivalent,
        mode=mode,
        effective_carb_equivalent_grams=effective_carb_equivalent,
    )