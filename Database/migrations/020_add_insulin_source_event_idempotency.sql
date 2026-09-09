BEGIN;

CREATE UNIQUE INDEX
    uq_insulin_events_patient_source_event
ON insulin_events (
    patient_id,
    source,
    source_event_id
)
WHERE source_event_id IS NOT NULL;

COMMIT;
