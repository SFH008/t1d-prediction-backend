BEGIN;

-- ============================================================================
-- B2.2 — Actual meal consumption
--
-- Preserves the original served/planned component quantities while allowing
-- actual consumed quantities to be recorded later.
--
-- Semantics:
--   NULL = actual consumption has not been recorded
--   0.0  = explicitly recorded that none was eaten
--   >0   = actual consumed quantity
--
-- consumed_carbs_grams is derived server-side from consumed_quantity_grams
-- using the immutable carb_factor_g_per_g snapshot stored with the component.
-- ============================================================================

ALTER TABLE meal_carb_groups
    ADD COLUMN IF NOT EXISTS consumed_quantity_grams
        NUMERIC(8, 1) NULL,

    ADD COLUMN IF NOT EXISTS consumed_carbs_grams
        NUMERIC(8, 1) NULL;


ALTER TABLE meal_carb_groups
    DROP CONSTRAINT IF EXISTS ck_meal_carb_groups_consumed_quantity_grams;

ALTER TABLE meal_carb_groups
    ADD CONSTRAINT ck_meal_carb_groups_consumed_quantity_grams
        CHECK (
            consumed_quantity_grams IS NULL
            OR consumed_quantity_grams >= 0
        );


ALTER TABLE meal_carb_groups
    DROP CONSTRAINT IF EXISTS ck_meal_carb_groups_consumed_carbs_grams;

ALTER TABLE meal_carb_groups
    ADD CONSTRAINT ck_meal_carb_groups_consumed_carbs_grams
        CHECK (
            consumed_carbs_grams IS NULL
            OR consumed_carbs_grams >= 0
        );


-- Actual consumption may never exceed the originally captured/planned
-- component quantity.
ALTER TABLE meal_carb_groups
    DROP CONSTRAINT IF EXISTS ck_meal_carb_groups_consumed_not_over_planned;

ALTER TABLE meal_carb_groups
    ADD CONSTRAINT ck_meal_carb_groups_consumed_not_over_planned
        CHECK (
            consumed_quantity_grams IS NULL
            OR consumed_quantity_grams <= quantity_grams
        );

COMMIT;
