BEGIN;

-- ============================================================================
-- 4A. MEALS
-- ============================================================================

CREATE TABLE meals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    meal_timestamp TIMESTAMP NOT NULL,
    meal_category VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'captured',
    total_carbs_grams DECIMAL(8, 1) NOT NULL DEFAULT 0,
    source VARCHAR(50) NOT NULL DEFAULT 'manual',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_meal_status
        CHECK (status IN ('captured')),

    CONSTRAINT chk_meal_total_carbs
        CHECK (total_carbs_grams >= 0)
);

CREATE INDEX idx_meals_patient_time
    ON meals(patient_id, meal_timestamp DESC);

CREATE INDEX idx_meals_patient_status
    ON meals(patient_id, status);

-- ============================================================================
-- 4B. MEAL CARBOHYDRATE GROUPS
-- ============================================================================

CREATE TABLE meal_carb_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_id UUID NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    group_number INTEGER NOT NULL,
    group_key VARCHAR(100) NOT NULL,
    group_name VARCHAR(255) NOT NULL,
    quantity_grams DECIMAL(8, 1) NOT NULL,
    carb_factor_g_per_g DECIMAL(8, 5) NOT NULL,
    carbs_grams DECIMAL(8, 1) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_meal_carb_group_number
        UNIQUE (meal_id, group_number),

    CONSTRAINT chk_meal_carb_group_number
        CHECK (group_number BETWEEN 1 AND 12),

    CONSTRAINT chk_meal_carb_quantity
        CHECK (quantity_grams >= 0),

    CONSTRAINT chk_meal_carb_factor
        CHECK (carb_factor_g_per_g >= 0 AND carb_factor_g_per_g <= 1),

    CONSTRAINT chk_meal_carb_contribution
        CHECK (carbs_grams >= 0)
);

CREATE INDEX idx_meal_carb_groups_meal
    ON meal_carb_groups(meal_id, group_number);

CREATE INDEX idx_meal_carb_groups_key
    ON meal_carb_groups(group_key);

-- ============================================================================
-- 5. MEAL CALCULATIONS
-- ============================================================================

CREATE TABLE meal_calculations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_id UUID NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,

    calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    glucose_mg_dl DECIMAL(6, 2),
    target_glucose_mg_dl DECIMAL(6, 2),

    carb_factor_g_per_unit DECIMAL(8, 3),
    insulin_sensitivity_mg_dl_per_unit DECIMAL(8, 2),

    carbohydrate_total_grams DECIMAL(7, 1) NOT NULL,

    carbohydrate_dose_units DECIMAL(8, 2),
    correction_dose_units DECIMAL(8, 2),
    calculated_dose_units DECIMAL(8, 2),

    calculation_version VARCHAR(50) NOT NULL DEFAULT '1',
    notes TEXT
);

CREATE INDEX idx_meal_calculations_meal
    ON meal_calculations(meal_id, calculated_at DESC);

CREATE INDEX idx_meal_calculations_patient
    ON meal_calculations(patient_id, calculated_at DESC);

COMMIT;
