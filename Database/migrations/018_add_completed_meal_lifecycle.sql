-- Migration 018
-- Automatic meal recording completion
--
-- Lifecycle:
--   captured -> active -> completed
--
-- completed means the Actual Meal recording workflow is complete.
-- It does NOT mean physiological meal activity has ended.
--
-- A meal qualifies when:
--   * every carbohydrate component has known actual consumption; and
--   * every planned dose event is given, adjusted, or skipped.
--
-- Explicit zero consumption is known consumption.
-- cancelled does not satisfy meal-recording completion.

BEGIN;

ALTER TABLE meals
    DROP CONSTRAINT chk_meal_status;

ALTER TABLE meals
    ADD CONSTRAINT chk_meal_status
        CHECK (status IN ('captured', 'active', 'completed'));

-- Reconcile active meals that already satisfied the completion rule
-- before automatic completion was introduced.
UPDATE meals AS m
SET
    status = 'completed',
    updated_at = CURRENT_TIMESTAMP
WHERE
    m.status = 'active'

    -- At least one carbohydrate component must exist.
    AND EXISTS (
        SELECT 1
        FROM meal_carb_groups AS cg
        WHERE cg.meal_id = m.id
    )

    -- Every carbohydrate component has known actual consumption.
    AND NOT EXISTS (
        SELECT 1
        FROM meal_carb_groups AS cg
        WHERE
            cg.meal_id = m.id
            AND cg.consumed_quantity_grams IS NULL
    )

    -- At least one planned dose event must exist.
    AND EXISTS (
        SELECT 1
        FROM meal_dose_events AS de
        WHERE de.meal_id = m.id
    )

    -- Every dose event is resolved using an allowed meal-completion state.
    AND NOT EXISTS (
        SELECT 1
        FROM meal_dose_events AS de
        WHERE
            de.meal_id = m.id
            AND de.status NOT IN ('given', 'adjusted', 'skipped')
    );

COMMIT;
