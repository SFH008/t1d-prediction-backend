BEGIN;

CREATE TABLE patient_deterministic_model_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    patient_id UUID NOT NULL UNIQUE
        REFERENCES patients(id) ON DELETE CASCADE,

    cob_model_key VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear',

    cob_model_version VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear_v1',

    iob_model_key VARCHAR(100),
    iob_model_version VARCHAR(100),

    insulin_accounting_policy VARCHAR(30) NOT NULL
        DEFAULT 'total',

    active_insulin_time_minutes INTEGER,

    patient_cob_model_selectable BOOLEAN NOT NULL
        DEFAULT FALSE,

    patient_iob_model_selectable BOOLEAN NOT NULL
        DEFAULT FALSE,

    allowed_cob_models JSONB,
    allowed_iob_models JSONB,

    cob_parameters JSONB,
    iob_parameters JSONB,

    config_source VARCHAR(50) NOT NULL
        DEFAULT 'admin',

    config_version VARCHAR(100) NOT NULL
        DEFAULT 'v1',

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_patient_deterministic_insulin_accounting_policy
        CHECK (
            insulin_accounting_policy IN (
                'total',
                'correction_only',
                'separated'
            )
        ),

    CONSTRAINT ck_patient_deterministic_active_insulin_time_positive
        CHECK (
            active_insulin_time_minutes IS NULL
            OR active_insulin_time_minutes > 0
        ),

    CONSTRAINT ck_patient_deterministic_iob_identity_complete
        CHECK (
            (iob_model_key IS NULL)
            =
            (iob_model_version IS NULL)
        )
);

CREATE INDEX idx_patient_deterministic_model_patient
ON patient_deterministic_model_settings(patient_id);

COMMIT;
