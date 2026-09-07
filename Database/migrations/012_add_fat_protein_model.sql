BEGIN;

-- ============================================================================
-- B2.3 — Warsaw-inspired delayed nutrient model
--
-- Patient clinical configuration is stored separately from the legacy
-- fat_protein_addon_percent field. Existing v3 semantics are preserved.
-- ============================================================================

ALTER TABLE dose_strategy_settings
    ADD COLUMN fat_protein_mode VARCHAR(20);

ALTER TABLE dose_strategy_settings
    ADD COLUMN fat_protein_scaling_percent NUMERIC(5, 2);

-- Conservative defaults for all existing patient strategies.
UPDATE dose_strategy_settings
SET
    fat_protein_mode = 'disabled',
    fat_protein_scaling_percent = 0
WHERE
    fat_protein_mode IS NULL
    OR fat_protein_scaling_percent IS NULL;

ALTER TABLE dose_strategy_settings
    ALTER COLUMN fat_protein_mode SET DEFAULT 'disabled',
    ALTER COLUMN fat_protein_mode SET NOT NULL,
    ALTER COLUMN fat_protein_scaling_percent SET DEFAULT 0,
    ALTER COLUMN fat_protein_scaling_percent SET NOT NULL;

ALTER TABLE dose_strategy_settings
    ADD CONSTRAINT ck_dose_strategy_fat_protein_mode
    CHECK (
        fat_protein_mode IN ('disabled', 'advisory', 'enabled')
    );

ALTER TABLE dose_strategy_settings
    ADD CONSTRAINT ck_dose_strategy_fat_protein_scaling_percent
    CHECK (
        fat_protein_scaling_percent >= 0
        AND fat_protein_scaling_percent <= 100
    );


-- ============================================================================
-- Immutable B2.3 model snapshot.
--
-- These columns are additive. They do not reinterpret or replace:
--   fat_protein_addon_percent
--   fat_protein_addon_grams
--   effective_carbohydrate_grams
-- ============================================================================

ALTER TABLE meal_calculations
    ADD COLUMN fat_protein_model_mode VARCHAR(20),
    ADD COLUMN fat_protein_model_scaling_percent NUMERIC(5, 2),

    ADD COLUMN fat_protein_fat_grams NUMERIC(8, 1),
    ADD COLUMN fat_protein_protein_grams NUMERIC(8, 1),

    ADD COLUMN fat_protein_fat_kcal NUMERIC(10, 2),
    ADD COLUMN fat_protein_protein_kcal NUMERIC(10, 2),
    ADD COLUMN fat_protein_total_kcal NUMERIC(10, 2),

    ADD COLUMN fat_protein_units NUMERIC(10, 4),

    ADD COLUMN fat_protein_theoretical_carb_equivalent_grams NUMERIC(10, 2),
    ADD COLUMN fat_protein_scaled_carb_equivalent_grams NUMERIC(10, 2),
    ADD COLUMN fat_protein_effective_carb_equivalent_grams NUMERIC(10, 2),

    ADD COLUMN fat_protein_model_version VARCHAR(50);

ALTER TABLE meal_calculations
    ADD CONSTRAINT ck_meal_calculation_fat_protein_model_mode
    CHECK (
        fat_protein_model_mode IS NULL
        OR fat_protein_model_mode IN ('disabled', 'advisory', 'enabled')
    );

ALTER TABLE meal_calculations
    ADD CONSTRAINT ck_meal_calculation_fat_protein_scaling_percent
    CHECK (
        fat_protein_model_scaling_percent IS NULL
        OR (
            fat_protein_model_scaling_percent >= 0
            AND fat_protein_model_scaling_percent <= 100
        )
    );

ALTER TABLE meal_calculations
    ADD CONSTRAINT ck_meal_calculation_fat_protein_nonnegative
    CHECK (
        (fat_protein_fat_grams IS NULL OR fat_protein_fat_grams >= 0)
        AND
        (fat_protein_protein_grams IS NULL OR fat_protein_protein_grams >= 0)
        AND
        (fat_protein_fat_kcal IS NULL OR fat_protein_fat_kcal >= 0)
        AND
        (fat_protein_protein_kcal IS NULL OR fat_protein_protein_kcal >= 0)
        AND
        (fat_protein_total_kcal IS NULL OR fat_protein_total_kcal >= 0)
        AND
        (fat_protein_units IS NULL OR fat_protein_units >= 0)
        AND
        (
            fat_protein_theoretical_carb_equivalent_grams IS NULL
            OR fat_protein_theoretical_carb_equivalent_grams >= 0
        )
        AND
        (
            fat_protein_scaled_carb_equivalent_grams IS NULL
            OR fat_protein_scaled_carb_equivalent_grams >= 0
        )
        AND
        (
            fat_protein_effective_carb_equivalent_grams IS NULL
            OR fat_protein_effective_carb_equivalent_grams >= 0
        )
    );

COMMIT;
