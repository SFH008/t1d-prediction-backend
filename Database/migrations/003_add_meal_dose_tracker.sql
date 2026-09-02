BEGIN;

-- ============================================================================
-- MULTI-DOSE TRACKER: PLAN VERSUS ACTUAL ADMINISTRATION
-- ============================================================================

CREATE TABLE meal_dose_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    patient_id UUID NOT NULL
        REFERENCES patients(id) ON DELETE CASCADE,
    meal_id UUID NOT NULL
        REFERENCES meals(id) ON DELETE CASCADE,
    calculation_id UUID NOT NULL
        REFERENCES meal_calculations(id) ON DELETE CASCADE,

    dose_number INTEGER NOT NULL,

    planned_timestamp TIMESTAMP NOT NULL,
    planned_units DECIMAL(8, 3) NOT NULL,

    actual_timestamp TIMESTAMP,
    actual_units DECIMAL(8, 3),

    status VARCHAR(30) NOT NULL DEFAULT 'planned',
    adjustment_reason VARCHAR(100),
    notes TEXT,

    insulin_event_id UUID
        REFERENCES insulin_events(id) ON DELETE SET NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_meal_dose_event
        UNIQUE (calculation_id, dose_number),

    CONSTRAINT chk_meal_dose_number
        CHECK (dose_number IN (1, 2)),

    CONSTRAINT chk_meal_dose_planned_units
        CHECK (planned_units >= 0),

    CONSTRAINT chk_meal_dose_actual_units
        CHECK (actual_units IS NULL OR actual_units >= 0),

    CONSTRAINT chk_meal_dose_status
        CHECK (status IN ('planned', 'given', 'adjusted', 'skipped', 'cancelled')),

    CONSTRAINT chk_meal_dose_execution_state
        CHECK (
            (status = 'planned' AND actual_timestamp IS NULL AND actual_units IS NULL)
            OR (status IN ('given', 'adjusted') AND actual_timestamp IS NOT NULL AND actual_units IS NOT NULL)
            OR (status IN ('skipped', 'cancelled') AND actual_units IS NULL)
        )
);

CREATE INDEX idx_meal_dose_events_patient_time
    ON meal_dose_events(patient_id, planned_timestamp);

CREATE INDEX idx_meal_dose_events_meal
    ON meal_dose_events(meal_id);

CREATE INDEX idx_meal_dose_events_calculation
    ON meal_dose_events(calculation_id);

CREATE INDEX idx_meal_dose_events_insulin_event
    ON meal_dose_events(insulin_event_id)
    WHERE insulin_event_id IS NOT NULL;

COMMIT;
