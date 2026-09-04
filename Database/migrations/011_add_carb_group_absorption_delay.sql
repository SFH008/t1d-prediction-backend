BEGIN;

-- Global/system default only. Patient-specific clinical configuration may
-- override this value for future meals. Existing behavior is preserved at 10.
ALTER TABLE carb_group_definitions
    ADD COLUMN IF NOT EXISTS default_absorption_delay_minutes INTEGER;

UPDATE carb_group_definitions
SET default_absorption_delay_minutes = 10
WHERE default_absorption_delay_minutes IS NULL;

ALTER TABLE carb_group_definitions
    ALTER COLUMN default_absorption_delay_minutes SET DEFAULT 10,
    ALTER COLUMN default_absorption_delay_minutes SET NOT NULL;

ALTER TABLE carb_group_definitions
    DROP CONSTRAINT IF EXISTS ck_carb_group_definitions_default_absorption_delay;

ALTER TABLE carb_group_definitions
    ADD CONSTRAINT ck_carb_group_definitions_default_absorption_delay
        CHECK (default_absorption_delay_minutes >= 0);

-- Patient-scoped clinical overrides. This is an admin-managed configuration
-- surface; normal user settings must never write these rows.
CREATE TABLE IF NOT EXISTS patient_carb_group_settings (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    carb_group_definition_id UUID NOT NULL
        REFERENCES carb_group_definitions(id) ON DELETE CASCADE,
    absorption_profile_key VARCHAR(50),
    absorption_delay_minutes INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_patient_carb_group_settings_patient_group
        UNIQUE (patient_id, carb_group_definition_id),
    CONSTRAINT ck_patient_carb_group_settings_profile
        CHECK (
            absorption_profile_key IS NULL
            OR absorption_profile_key IN ('very_fast', 'fast', 'medium', 'slow')
        ),
    CONSTRAINT ck_patient_carb_group_settings_delay
        CHECK (
            absorption_delay_minutes IS NULL
            OR absorption_delay_minutes >= 0
        )
);

CREATE INDEX IF NOT EXISTS ix_patient_carb_group_settings_patient
    ON patient_carb_group_settings(patient_id);

COMMIT;