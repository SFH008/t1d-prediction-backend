BEGIN;

CREATE TABLE IF NOT EXISTS meal_component_absorptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    meal_carb_group_id UUID NOT NULL UNIQUE,
    patient_id UUID NOT NULL,

    absorption_profile_id UUID,
    absorption_profile_key VARCHAR(50) NOT NULL,

    absorption_delay_minutes INTEGER NOT NULL,
    absorption_duration_minutes INTEGER NOT NULL,

    curve_type VARCHAR(50) NOT NULL DEFAULT 'linear',
    curve_parameters JSONB,

    classification_source VARCHAR(100) NOT NULL
        DEFAULT 'carb_group_default_v1',

    model_version VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear_v1',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_meal_component_absorptions_group
        FOREIGN KEY (meal_carb_group_id)
        REFERENCES meal_carb_groups(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_meal_component_absorptions_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_meal_component_absorptions_profile
        FOREIGN KEY (absorption_profile_id)
        REFERENCES carb_absorption_profiles(id)
        ON DELETE SET NULL,

    CONSTRAINT ck_meal_component_absorptions_delay
        CHECK (absorption_delay_minutes >= 0),

    CONSTRAINT ck_meal_component_absorptions_duration
        CHECK (absorption_duration_minutes > 0)
);

CREATE INDEX IF NOT EXISTS
    ix_meal_component_absorptions_patient
ON meal_component_absorptions(patient_id);

CREATE INDEX IF NOT EXISTS
    ix_meal_component_absorptions_profile_key
ON meal_component_absorptions(absorption_profile_key);

COMMIT;
