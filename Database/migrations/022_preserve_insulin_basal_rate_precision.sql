BEGIN;

ALTER TABLE insulin_events
    ALTER COLUMN basal_rate
    TYPE NUMERIC(8, 4);

COMMIT;
