BEGIN;

-- ============================================================================
-- B2.2 — Meal macronutrient facts
--
-- Stores raw meal-level fat and protein quantities.
-- These are nutritional facts only. They MUST NOT directly alter insulin
-- recommendations. Any future fat/protein insulin contribution is handled
-- separately by the versioned B2.3 model and admin-controlled settings.
-- ============================================================================

ALTER TABLE meals
    ADD COLUMN IF NOT EXISTS fat_grams
        NUMERIC(8, 1) NOT NULL DEFAULT 0.0,

    ADD COLUMN IF NOT EXISTS protein_grams
        NUMERIC(8, 1) NOT NULL DEFAULT 0.0;


ALTER TABLE meals
    DROP CONSTRAINT IF EXISTS ck_meals_fat_grams;

ALTER TABLE meals
    ADD CONSTRAINT ck_meals_fat_grams
        CHECK (fat_grams >= 0);


ALTER TABLE meals
    DROP CONSTRAINT IF EXISTS ck_meals_protein_grams;

ALTER TABLE meals
    ADD CONSTRAINT ck_meals_protein_grams
        CHECK (protein_grams >= 0);

COMMIT;