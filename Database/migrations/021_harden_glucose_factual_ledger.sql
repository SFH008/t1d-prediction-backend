BEGIN;

ALTER TABLE glucose_readings
    ADD COLUMN source_event_id VARCHAR(255);

CREATE UNIQUE INDEX uq_glucose_patient_source_event
ON glucose_readings (
    patient_id,
    source,
    source_event_id
)
WHERE source_event_id IS NOT NULL;

COMMIT;
