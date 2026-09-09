BEGIN;

-- ============================================================================
-- B2.4 — One active meal per patient
--
-- Application-level checks provide useful API errors, but cannot prevent two
-- concurrent transactions from activating different meals simultaneously.
--
-- PostgreSQL is therefore the authoritative concurrency gate.
-- ============================================================================

CREATE UNIQUE INDEX uq_meals_one_active_per_patient
    ON meals (patient_id)
    WHERE status = 'active';

COMMIT;
