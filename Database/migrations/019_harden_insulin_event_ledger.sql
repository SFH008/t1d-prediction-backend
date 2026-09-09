-- B2.4b.1 — Harden factual insulin-event ledger
--
-- The insulin event ledger is the authoritative factual input to future
-- deterministic IOB calculations.
--
-- dose_units remains the canonical ACTUAL delivered insulin quantity.
-- The columns added here preserve independent normalized semantics and
-- source-native provenance without changing historical insulin records.
--
-- No IOB mathematics or patient model selection is introduced here.

BEGIN;

ALTER TABLE insulin_events
    ADD COLUMN delivery_class VARCHAR(30),
    ADD COLUMN administration_mode VARCHAR(30),
    ADD COLUMN purpose VARCHAR(30),
    ADD COLUMN source_event_type VARCHAR(100),
    ADD COLUMN source_activation_type VARCHAR(100),
    ADD COLUMN source_event_id VARCHAR(255),
    ADD COLUMN source_device_id VARCHAR(255),
    ADD COLUMN programmed_units NUMERIC(8, 3),
    ADD COLUMN delivery_completed BOOLEAN;

ALTER TABLE insulin_events
    ADD CONSTRAINT chk_insulin_delivery_class
    CHECK (
        delivery_class IS NULL
        OR delivery_class IN (
            'basal',
            'bolus',
            'other'
        )
    );

ALTER TABLE insulin_events
    ADD CONSTRAINT chk_insulin_administration_mode
    CHECK (
        administration_mode IS NULL
        OR administration_mode IN (
            'automated',
            'recommended',
            'manual',
            'imported',
            'unknown'
        )
    );

ALTER TABLE insulin_events
    ADD CONSTRAINT chk_insulin_purpose
    CHECK (
        purpose IS NULL
        OR purpose IN (
            'meal',
            'correction',
            'basal',
            'combined',
            'unknown'
        )
    );

ALTER TABLE insulin_events
    ADD CONSTRAINT chk_insulin_programmed_units_nonnegative
    CHECK (
        programmed_units IS NULL
        OR programmed_units >= 0
    );

COMMIT;
