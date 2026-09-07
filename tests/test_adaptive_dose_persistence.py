"""
Persistence-contract tests for B2.4a adaptive meal calculations.

The adaptive calculation is an append-only meal-accounting snapshot.
It must not mutate or replace the original version-3 MealCalculation and
must not yet be represented as a safe immediate insulin recommendation.
"""

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "Database"
    / "migrations"
    / "013_add_adaptive_meal_calculations.sql"
)

PROVENANCE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "Database"
    / "migrations"
    / "014_add_adaptive_model_provenance.sql"
)


def _provenance_migration_sql() -> str:
    return PROVENANCE_MIGRATION_PATH.read_text().lower()

def _migration_sql() -> str:
    return MIGRATION_PATH.read_text().lower()


def test_adaptive_meal_calculation_migration_exists():
    assert MIGRATION_PATH.exists()


def test_adaptive_meal_calculation_migration_creates_append_only_table():
    sql = _migration_sql()

    assert "create table" in sql
    assert "adaptive_meal_calculations" in sql

    # Multiple adaptive snapshots must be allowed for one original calculation.
    assert "unique (calculation_id)" not in sql
    assert "unique(calculation_id)" not in sql


def test_adaptive_meal_calculation_migration_preserves_lineage():
    sql = _migration_sql()

    assert "patient_id" in sql
    assert "references patients" in sql

    assert "meal_id" in sql
    assert "references meals" in sql

    assert "calculation_id" in sql
    assert "references meal_calculations" in sql


def test_adaptive_meal_calculation_migration_has_input_and_output_snapshots():
    sql = _migration_sql()

    required_columns = (
        "calculated_at",
        "consumed_carbs_grams",
        "fat_protein_effective_carb_equivalent_grams",
        "insulin_to_carb_ratio",
        "actual_administered_units",
        "carb_insulin_requirement_units",
        "fat_protein_insulin_requirement_units",
        "total_meal_requirement_units",
        "remaining_meal_requirement_units",
        "adaptive_calculation_version",
    )

    for column in required_columns:
        assert column in sql


def test_adaptive_meal_calculation_migration_has_safety_constraints():
    sql = " ".join(_migration_sql().split())

    # Unknown consumption/results remain nullable, but known numeric values
    # must never be negative.
    assert (
        "consumed_carbs_grams is null or consumed_carbs_grams >= 0"
        in sql
    )
    assert (
        "carb_insulin_requirement_units is null "
        "or carb_insulin_requirement_units >= 0"
        in sql
    )
    assert (
        "total_meal_requirement_units is null "
        "or total_meal_requirement_units >= 0"
        in sql
    )
    assert (
        "remaining_meal_requirement_units is null "
        "or remaining_meal_requirement_units >= 0"
        in sql
    )

    assert "fat_protein_effective_carb_equivalent_grams >= 0" in sql
    assert "insulin_to_carb_ratio > 0" in sql
    assert "actual_administered_units >= 0" in sql
    assert "fat_protein_insulin_requirement_units >= 0" in sql


def test_adaptive_meal_calculation_migration_indexes_history_queries():
    sql = _migration_sql()

    assert "create index" in sql
    assert "patient_id" in sql
    assert "meal_id" in sql
    assert "calculation_id" in sql
    assert "calculated_at" in sql

def test_adaptive_model_provenance_migration_exists():
    assert PROVENANCE_MIGRATION_PATH.exists()


def test_adaptive_model_provenance_migration_adds_model_version():
    sql = _provenance_migration_sql()

    assert "adaptive_model_version" in sql
    assert "alter table adaptive_meal_calculations" in sql


def test_adaptive_model_provenance_migration_makes_warsaw_fields_nullable():
    sql = " ".join(_provenance_migration_sql().split())

    assert (
        "fat_protein_effective_carb_equivalent_grams drop not null"
        in sql
    )
    assert (
        "fat_protein_insulin_requirement_units drop not null"
        in sql
    )