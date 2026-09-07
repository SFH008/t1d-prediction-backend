BEGIN;

CREATE TABLE clinical_model_settings (
    id UUID PRIMARY KEY,
    model_key VARCHAR(100) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_clinical_model_settings_identity
        UNIQUE (model_key, model_version),

    CONSTRAINT ck_clinical_model_settings_role
        CHECK (role IN ('primary', 'alternative'))
);

INSERT INTO clinical_model_settings (
    id,
    model_key,
    model_version,
    role,
    enabled
)
VALUES
(
    '00000000-0000-0000-0000-000000000101',
    'primary',
    'primary_v1',
    'primary',
    TRUE
),
(
    '00000000-0000-0000-0000-000000000102',
    'warsaw',
    'warsaw_v1',
    'alternative',
    FALSE
);

COMMIT;