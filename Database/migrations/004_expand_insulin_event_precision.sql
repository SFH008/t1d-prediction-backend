BEGIN;

-- Keep canonical insulin delivery precision aligned with the tracker and
-- patient/device rounding increments used by Calculation V3.
ALTER TABLE insulin_events
    ALTER COLUMN dose_units TYPE DECIMAL(8,3);

COMMIT;
