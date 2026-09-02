BEGIN;

-- ============================================================================
-- STEP 3A. TIME-OF-DAY THERAPY CONTEXT
-- ============================================================================

ALTER TABLE time_of_day_profiles
    ADD COLUMN basal_drift_mg_dl_per_hour DECIMAL(8, 2) NOT NULL DEFAULT 0;

ALTER TABLE time_of_day_profiles
    ALTER COLUMN insulin_sensitivity_mg_dl_per_unit SET NOT NULL,
    ALTER COLUMN insulin_to_carb_ratio SET NOT NULL;

ALTER TABLE time_of_day_profiles
    ADD CONSTRAINT chk_tod_isf_positive
        CHECK (insulin_sensitivity_mg_dl_per_unit > 0),
    ADD CONSTRAINT chk_tod_icr_positive
        CHECK (insulin_to_carb_ratio > 0),
    ADD CONSTRAINT chk_tod_day_of_week
        CHECK (day_of_week IS NULL OR day_of_week BETWEEN 0 AND 6);

-- ============================================================================
-- STEP 3B. PATIENT-SPECIFIC DOSE STRATEGY SETTINGS
-- ============================================================================

CREATE TABLE dose_strategy_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,

    dose_1_share_percent DECIMAL(5, 2) NOT NULL DEFAULT 60.00,
    dose_2_delay_minutes INTEGER NOT NULL DEFAULT 75,
    insulin_rounding_increment_units DECIMAL(6, 3) NOT NULL DEFAULT 0.05,
    fat_protein_addon_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,

    total_daily_dose_units DECIMAL(8, 2),
    basal_share_percent DECIMAL(5, 2),

    strategy_source VARCHAR(50) NOT NULL DEFAULT 'manual',
    strategy_version VARCHAR(100),

    min_dose_1_share_percent DECIMAL(5, 2),
    max_dose_1_share_percent DECIMAL(5, 2),
    min_dose_2_delay_minutes INTEGER,
    max_dose_2_delay_minutes INTEGER,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_dose_strategy_patient UNIQUE (patient_id),
    CONSTRAINT chk_dose1_share
        CHECK (dose_1_share_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_rounding_increment
        CHECK (insulin_rounding_increment_units > 0),
    CONSTRAINT chk_dose2_delay
        CHECK (dose_2_delay_minutes >= 0),
    CONSTRAINT chk_fat_protein_addon
        CHECK (fat_protein_addon_percent >= 0),
    CONSTRAINT chk_basal_share
        CHECK (basal_share_percent IS NULL OR basal_share_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_tdd
        CHECK (total_daily_dose_units IS NULL OR total_daily_dose_units > 0),
    CONSTRAINT chk_min_dose1_share
        CHECK (min_dose_1_share_percent IS NULL OR min_dose_1_share_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_max_dose1_share
        CHECK (max_dose_1_share_percent IS NULL OR max_dose_1_share_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_dose1_share_bounds
        CHECK (
            min_dose_1_share_percent IS NULL
            OR max_dose_1_share_percent IS NULL
            OR min_dose_1_share_percent <= max_dose_1_share_percent
        ),
    CONSTRAINT chk_min_dose2_delay
        CHECK (min_dose_2_delay_minutes IS NULL OR min_dose_2_delay_minutes >= 0),
    CONSTRAINT chk_max_dose2_delay
        CHECK (max_dose_2_delay_minutes IS NULL OR max_dose_2_delay_minutes >= 0),
    CONSTRAINT chk_dose2_delay_bounds
        CHECK (
            min_dose_2_delay_minutes IS NULL
            OR max_dose_2_delay_minutes IS NULL
            OR min_dose_2_delay_minutes <= max_dose_2_delay_minutes
        )
);


-- ============================================================================
-- STEP 3C. PATIENT-SPECIFIC CARBOHYDRATE ABSORPTION PROFILES
-- ============================================================================

CREATE TABLE carb_absorption_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    profile_key VARCHAR(50) NOT NULL,
    profile_name VARCHAR(100) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    absorption_delay_minutes INTEGER NOT NULL DEFAULT 10,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_carb_absorption_patient_key
        UNIQUE (patient_id, profile_key),
    CONSTRAINT chk_absorption_duration
        CHECK (duration_minutes > 0),
    CONSTRAINT chk_absorption_delay
        CHECK (absorption_delay_minutes >= 0)
);

CREATE INDEX idx_carb_absorption_patient
    ON carb_absorption_profiles(patient_id);

-- ============================================================================
-- STEP 3D. MEAL CLASSIFICATION INPUTS
-- ============================================================================

ALTER TABLE meals
    ADD COLUMN absorption_profile_id UUID
        REFERENCES carb_absorption_profiles(id) ON DELETE SET NULL,
    ADD COLUMN absorption_profile_key VARCHAR(50),
    ADD COLUMN absorption_classification_source VARCHAR(50),
    ADD COLUMN fat_protein_addon_percent DECIMAL(5, 2);

ALTER TABLE meals
    ADD CONSTRAINT chk_meal_fat_protein_addon
        CHECK (fat_protein_addon_percent IS NULL OR fat_protein_addon_percent >= 0);

CREATE INDEX idx_meals_absorption_profile
    ON meals(absorption_profile_id);

-- ============================================================================
-- STEP 3E. IMMUTABLE SPLIT-DOSE CALCULATION SNAPSHOT
-- ============================================================================

ALTER TABLE meal_calculations
    ADD COLUMN meal_therapy_profile_id UUID,
    ADD COLUMN meal_basal_drift_mg_dl_per_hour DECIMAL(8, 2),

    ADD COLUMN base_carbohydrate_grams DECIMAL(8, 1),
    ADD COLUMN fat_protein_addon_percent DECIMAL(5, 2),
    ADD COLUMN fat_protein_addon_grams DECIMAL(8, 1),
    ADD COLUMN effective_carbohydrate_grams DECIMAL(8, 1),

    ADD COLUMN absorption_profile_id UUID,
    ADD COLUMN absorption_profile_key VARCHAR(50),
    ADD COLUMN absorption_duration_minutes INTEGER,
    ADD COLUMN absorption_delay_minutes INTEGER,
    ADD COLUMN absorption_classification_source VARCHAR(50),

    ADD COLUMN dose_1_share_percent DECIMAL(5, 2),
    ADD COLUMN dose_2_share_percent DECIMAL(5, 2),
    ADD COLUMN dose_2_delay_minutes INTEGER,
    ADD COLUMN dose_2_timestamp TIMESTAMP,
    ADD COLUMN insulin_rounding_increment_units DECIMAL(6, 3),
    ADD COLUMN strategy_source VARCHAR(50),
    ADD COLUMN strategy_version VARCHAR(100),

    ADD COLUMN dose_2_therapy_profile_id UUID,
    ADD COLUMN dose_2_carb_factor_g_per_unit DECIMAL(8, 3),
    ADD COLUMN dose_2_insulin_sensitivity_mg_dl_per_unit DECIMAL(8, 2),
    ADD COLUMN dose_2_target_glucose_mg_dl DECIMAL(6, 2),
    ADD COLUMN dose_2_basal_drift_mg_dl_per_hour DECIMAL(8, 2),

    ADD COLUMN dose_1_carbohydrate_grams DECIMAL(8, 1),
    ADD COLUMN dose_2_carbohydrate_grams DECIMAL(8, 1),
    ADD COLUMN dose_1_carbohydrate_units DECIMAL(8, 3),
    ADD COLUMN dose_1_units DECIMAL(8, 3),
    ADD COLUMN dose_2_carbohydrate_units DECIMAL(8, 3),
    ADD COLUMN dose_2_units DECIMAL(8, 3),
    ADD COLUMN total_planned_dose_units DECIMAL(8, 3),
    ADD COLUMN manual_insulin_given_units DECIMAL(8, 3);

ALTER TABLE meal_calculations
    ADD CONSTRAINT chk_calc_fat_protein_addon
        CHECK (fat_protein_addon_percent IS NULL OR fat_protein_addon_percent >= 0),
    ADD CONSTRAINT chk_calc_absorption_duration
        CHECK (absorption_duration_minutes IS NULL OR absorption_duration_minutes > 0),
    ADD CONSTRAINT chk_calc_absorption_delay
        CHECK (absorption_delay_minutes IS NULL OR absorption_delay_minutes >= 0),
    ADD CONSTRAINT chk_calc_dose1_share
        CHECK (dose_1_share_percent IS NULL OR dose_1_share_percent BETWEEN 0 AND 100),
    ADD CONSTRAINT chk_calc_dose2_share
        CHECK (dose_2_share_percent IS NULL OR dose_2_share_percent BETWEEN 0 AND 100),
    ADD CONSTRAINT chk_calc_share_total
        CHECK (
            dose_1_share_percent IS NULL
            OR dose_2_share_percent IS NULL
            OR dose_1_share_percent + dose_2_share_percent = 100
        ),
    ADD CONSTRAINT chk_calc_dose2_delay
        CHECK (dose_2_delay_minutes IS NULL OR dose_2_delay_minutes >= 0),
    ADD CONSTRAINT chk_calc_rounding_increment
        CHECK (insulin_rounding_increment_units IS NULL OR insulin_rounding_increment_units > 0),
    ADD CONSTRAINT chk_calc_manual_insulin
        CHECK (manual_insulin_given_units IS NULL OR manual_insulin_given_units >= 0);

COMMIT;
