BEGIN;

-- ============================================================================
-- Historical patient absorption timeline
--
-- Stores derived 5-minute absorption estimates for history, UI, and model
-- training. These values are estimates, not directly observed absorption.
-- Multiple derivation versions may coexist for the same historical interval.
-- ============================================================================

CREATE TABLE IF NOT EXISTS patient_absorption_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    patient_id UUID NOT NULL,

    interval_start TIMESTAMP NOT NULL,
    interval_end TIMESTAMP NOT NULL,

    base_absorbed_carbs_grams NUMERIC(12, 6) NOT NULL,

    hormonal_multiplier NUMERIC(10, 5) NOT NULL DEFAULT 1.0,
    activity_multiplier NUMERIC(10, 5) NOT NULL DEFAULT 1.0,

    adjusted_absorbed_carbs_grams NUMERIC(12, 6) NOT NULL,

    component_count INTEGER NOT NULL DEFAULT 0,

    derivation_model VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear',

    derivation_version VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear_v1',

    derivation_mode VARCHAR(50) NOT NULL
        DEFAULT 'original',

    derived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_patient_absorption_history_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE,

    CONSTRAINT ck_patient_absorption_history_interval
        CHECK (
            interval_end
            = interval_start + INTERVAL '5 minutes'
        ),

    CONSTRAINT ck_patient_absorption_history_alignment
        CHECK (
            EXTRACT(SECOND FROM interval_start) = 0
            AND MOD(
                EXTRACT(MINUTE FROM interval_start)::INTEGER,
                5
            ) = 0
        ),

    CONSTRAINT ck_patient_absorption_history_base
        CHECK (base_absorbed_carbs_grams >= 0),

    CONSTRAINT ck_patient_absorption_history_adjusted
        CHECK (adjusted_absorbed_carbs_grams >= 0),

    CONSTRAINT ck_patient_absorption_history_hormonal
        CHECK (hormonal_multiplier >= 0),

    CONSTRAINT ck_patient_absorption_history_activity
        CHECK (activity_multiplier >= 0),

    CONSTRAINT ck_patient_absorption_history_component_count
        CHECK (component_count >= 0),

    CONSTRAINT ck_patient_absorption_history_mode
        CHECK (
            derivation_mode IN (
                'original',
                'retrospective'
            )
        ),

    CONSTRAINT uq_patient_absorption_history_derivation
        UNIQUE (
            patient_id,
            interval_start,
            derivation_model,
            derivation_version,
            derivation_mode
        )
);

CREATE INDEX IF NOT EXISTS
    ix_patient_absorption_history_patient_time
ON patient_absorption_history (
    patient_id,
    interval_start DESC
);


-- ============================================================================
-- Current rolling patient absorption forecast
--
-- Operational state only. The active 72-point forecast for a patient is
-- replaced atomically when relevant inputs change.
--
-- Exact event timestamps remain in source records. interval_start/end are
-- standardized clock-aligned 5-minute buckets.
-- ============================================================================

CREATE TABLE IF NOT EXISTS patient_absorption_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    patient_id UUID NOT NULL,

    -- Exact timestamp that caused or anchored this recalculation.
    forecast_anchor_timestamp TIMESTAMP NOT NULL,

    -- First complete clock-aligned 5-minute bucket in this forecast.
    forecast_grid_start TIMESTAMP NOT NULL,

    interval_start TIMESTAMP NOT NULL,
    interval_end TIMESTAMP NOT NULL,

    base_absorbed_carbs_grams NUMERIC(12, 6) NOT NULL,

    hormonal_multiplier NUMERIC(10, 5) NOT NULL DEFAULT 1.0,
    activity_multiplier NUMERIC(10, 5) NOT NULL DEFAULT 1.0,

    adjusted_absorbed_carbs_grams NUMERIC(12, 6) NOT NULL,

    component_count INTEGER NOT NULL DEFAULT 0,

    deterministic_model_version VARCHAR(100) NOT NULL
        DEFAULT 'deterministic_linear_v1',

    -- Reserved for later TensorFlow probabilistic inference.
    ml_model_version VARCHAR(100),

    ml_predicted_absorbed_carbs_grams NUMERIC(12, 6),
    ml_lower_bound_grams NUMERIC(12, 6),
    ml_upper_bound_grams NUMERIC(12, 6),
    ml_confidence NUMERIC(8, 6),

    forecast_generated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_patient_absorption_forecasts_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE,

    CONSTRAINT ck_patient_absorption_forecasts_interval
        CHECK (
            interval_end
            = interval_start + INTERVAL '5 minutes'
        ),

    CONSTRAINT ck_patient_absorption_forecasts_alignment
        CHECK (
            EXTRACT(SECOND FROM interval_start) = 0
            AND MOD(
                EXTRACT(MINUTE FROM interval_start)::INTEGER,
                5
            ) = 0
        ),

    CONSTRAINT ck_patient_absorption_forecasts_grid_alignment
        CHECK (
            EXTRACT(SECOND FROM forecast_grid_start) = 0
            AND MOD(
                EXTRACT(MINUTE FROM forecast_grid_start)::INTEGER,
                5
            ) = 0
        ),

    CONSTRAINT ck_patient_absorption_forecasts_base
        CHECK (base_absorbed_carbs_grams >= 0),

    CONSTRAINT ck_patient_absorption_forecasts_adjusted
        CHECK (adjusted_absorbed_carbs_grams >= 0),

    CONSTRAINT ck_patient_absorption_forecasts_hormonal
        CHECK (hormonal_multiplier >= 0),

    CONSTRAINT ck_patient_absorption_forecasts_activity
        CHECK (activity_multiplier >= 0),

    CONSTRAINT ck_patient_absorption_forecasts_component_count
        CHECK (component_count >= 0),

    CONSTRAINT ck_patient_absorption_forecasts_ml_prediction
        CHECK (
            ml_predicted_absorbed_carbs_grams IS NULL
            OR ml_predicted_absorbed_carbs_grams >= 0
        ),

    CONSTRAINT ck_patient_absorption_forecasts_ml_lower
        CHECK (
            ml_lower_bound_grams IS NULL
            OR ml_lower_bound_grams >= 0
        ),

    CONSTRAINT ck_patient_absorption_forecasts_ml_upper
        CHECK (
            ml_upper_bound_grams IS NULL
            OR ml_upper_bound_grams >= 0
        ),

    CONSTRAINT ck_patient_absorption_forecasts_ml_bounds
        CHECK (
            ml_lower_bound_grams IS NULL
            OR ml_predicted_absorbed_carbs_grams IS NULL
            OR ml_lower_bound_grams
               <= ml_predicted_absorbed_carbs_grams
        ),

    CONSTRAINT ck_patient_absorption_forecasts_ml_bounds_upper
        CHECK (
            ml_upper_bound_grams IS NULL
            OR ml_predicted_absorbed_carbs_grams IS NULL
            OR ml_predicted_absorbed_carbs_grams
               <= ml_upper_bound_grams
        ),

    CONSTRAINT ck_patient_absorption_forecasts_ml_confidence
        CHECK (
            ml_confidence IS NULL
            OR (
                ml_confidence >= 0
                AND ml_confidence <= 1
            )
        ),

    CONSTRAINT uq_patient_absorption_forecast_current
        UNIQUE (
            patient_id,
            interval_start
        )
);

CREATE INDEX IF NOT EXISTS
    ix_patient_absorption_forecasts_patient_time
ON patient_absorption_forecasts (
    patient_id,
    interval_start
);

CREATE INDEX IF NOT EXISTS
    ix_patient_absorption_forecasts_generated
ON patient_absorption_forecasts (
    patient_id,
    forecast_generated_at DESC
);

COMMIT;
