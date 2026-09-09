-- ============================================================================
-- 024: Add stable human-facing patient reference
--
-- patients.id remains the canonical internal UUID.
-- patient_reference is an immutable human-facing identifier such as T1D-000001.
-- It must never depend on pump/device identity.
-- ============================================================================

BEGIN;

CREATE SEQUENCE patient_reference_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE patients
    ADD COLUMN patient_reference VARCHAR(20);

ALTER SEQUENCE patient_reference_seq
    OWNED BY patients.patient_reference;

UPDATE patients
SET patient_reference =
    'T1D-' ||
    LPAD(
        nextval('patient_reference_seq')::text,
        6,
        '0'
    )
WHERE patient_reference IS NULL;

ALTER TABLE patients
    ALTER COLUMN patient_reference
    SET DEFAULT (
        'T1D-' ||
        LPAD(
            nextval('patient_reference_seq')::text,
            6,
            '0'
        )
    );

ALTER TABLE patients
    ALTER COLUMN patient_reference SET NOT NULL;

ALTER TABLE patients
    ADD CONSTRAINT uq_patients_patient_reference
    UNIQUE (patient_reference);

COMMIT;
