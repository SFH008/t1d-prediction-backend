BEGIN;

-- ============================================================================
-- B2.4 — Patient-scoped meal lifecycle
--
-- meal_timestamp remains the planning/capture timestamp.
-- started_at records when the meal actually becomes active.
--
-- Existing meals remain valid:
--   * started_at is nullable
--   * existing 'captured' status remains valid
--   * 'active' is added as the only new lifecycle state currently supported
-- ============================================================================

ALTER TABLE meals
    ADD COLUMN started_at TIMESTAMP;

ALTER TABLE meals
    DROP CONSTRAINT chk_meal_status;

ALTER TABLE meals
    ADD CONSTRAINT chk_meal_status
        CHECK (status IN ('captured', 'active'));

COMMIT;
