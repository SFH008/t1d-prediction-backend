    -- T1D Glucose Forecasting System - Corrected Database Schema
    -- Incorporates all critical and high-priority gaps from validation
    -- PostgreSQL DDL Definitions

    -- ============================================================================
    -- 1. PATIENTS (UPDATED: Device status cache)
    -- ============================================================================
    CREATE TABLE patients (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        external_patient_id VARCHAR(255) UNIQUE NOT NULL,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        date_of_birth DATE,
        sex CHAR(1),
        diabetes_type VARCHAR(20) NOT NULL DEFAULT 'type_1',
        diagnosis_date DATE,
        time_zone VARCHAR(50) DEFAULT 'UTC',
        weight_kg DECIMAL(5, 2),
        height_cm DECIMAL(5, 1),
        -- ADDED: Device status cache
        pump_status VARCHAR(50) DEFAULT 'unknown', -- 'connected' | 'disconnected' | 'error' | 'unknown'
        sensor_status VARCHAR(50) DEFAULT 'unknown', -- 'active' | 'calibrating' | 'error' | 'not_paired' | 'unknown'
        pump_battery_percent DECIMAL(5, 2),
        sensor_battery_percent DECIMAL(5, 2),
        last_pump_sync TIMESTAMP,
        last_sensor_sync TIMESTAMP,
        pump_last_sync_ago_minutes INTEGER,
        device_serial_number VARCHAR(255),
        device_model VARCHAR(100),
        reservoir_remaining_units DECIMAL(8, 2),
        sensor_state VARCHAR(255),
        calibration_status VARCHAR(100),
        sensor_duration_hours DECIMAL(8, 2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    );
    CREATE INDEX idx_patients_external_id ON patients(external_patient_id);
    CREATE INDEX idx_patients_is_active ON patients(is_active);
    CREATE INDEX idx_patients_pump_status ON patients(pump_status);
    CREATE INDEX idx_patients_sensor_status ON patients(sensor_status);

    -- ============================================================================
    -- 2. GLUCOSE_READINGS (UPDATED: Hypo/hyper classification flags)
    -- ============================================================================
    CREATE TABLE glucose_readings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        glucose_value_mg_dl DECIMAL(6, 2) NOT NULL,
        glucose_value_mmol_l DECIMAL(6, 2),
        reading_type VARCHAR(50) NOT NULL,
        source VARCHAR(50),
        device_name VARCHAR(100),
        is_calibration BOOLEAN DEFAULT FALSE,
        timestamp TIMESTAMP NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_valid BOOLEAN DEFAULT TRUE,
        -- ADDED: Classification flags for alert queries
        is_hypo BOOLEAN DEFAULT FALSE, -- TRUE if < 70 mg/dL
        is_severe_hypo BOOLEAN DEFAULT FALSE, -- TRUE if < 54 mg/dL
        is_hyper BOOLEAN DEFAULT FALSE, -- TRUE if > 180 mg/dL
        is_severe_hyper BOOLEAN DEFAULT FALSE, -- TRUE if > 250 mg/dL
        trend_arrow VARCHAR(10), -- '↑' | '↗' | '→' | '↘' | '↓'
        notes TEXT
    );
    CREATE INDEX idx_glucose_patient_time ON glucose_readings(patient_id, timestamp DESC);
    CREATE INDEX idx_glucose_timestamp ON glucose_readings(timestamp DESC);
    CREATE INDEX idx_glucose_source ON glucose_readings(source);
    -- ADDED: Conditional indexes for fast alert lookups
    CREATE INDEX idx_glucose_patient_hypo ON glucose_readings(patient_id, timestamp DESC) WHERE is_hypo = TRUE;
    CREATE INDEX idx_glucose_patient_severe_hypo ON glucose_readings(patient_id, timestamp DESC) WHERE is_severe_hypo = TRUE;
    CREATE INDEX idx_glucose_patient_hyper ON glucose_readings(patient_id, timestamp DESC) WHERE is_hyper = TRUE;
    CREATE INDEX idx_glucose_patient_severe_hyper ON glucose_readings(patient_id, timestamp DESC) WHERE is_severe_hyper = TRUE;

    -- ============================================================================
    -- 3. INSULIN_EVENTS
    -- ============================================================================
    CREATE TABLE insulin_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        insulin_type VARCHAR(50) NOT NULL,
        dose_units DECIMAL(8, 2) NOT NULL,
        delivery_method VARCHAR(50),
        bolus_component_rapid DECIMAL(8, 2),
        bolus_component_extended DECIMAL(8, 2),
        basal_rate DECIMAL(8, 2),
        timestamp TIMESTAMP NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source VARCHAR(50),
        device_name VARCHAR(100),
        is_manual_entry BOOLEAN DEFAULT FALSE,
        notes TEXT
    );
    CREATE INDEX idx_insulin_patient_time ON insulin_events(patient_id, timestamp DESC);
    CREATE INDEX idx_insulin_timestamp ON insulin_events(timestamp DESC);
    CREATE INDEX idx_insulin_type ON insulin_events(insulin_type);

    -- ============================================================================
    -- 4. CARB_INTAKES
    -- ============================================================================
    CREATE TABLE carb_intakes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        carbs_grams DECIMAL(6, 1) NOT NULL,
        food_description TEXT,
        food_category VARCHAR(100),
        meal_type VARCHAR(50),
        confidence_level VARCHAR(20),
        timestamp TIMESTAMP NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source VARCHAR(50),
        is_estimated BOOLEAN DEFAULT FALSE,
        notes TEXT
    );
    CREATE INDEX idx_carbs_patient_time ON carb_intakes(patient_id, timestamp DESC);
    CREATE INDEX idx_carbs_timestamp ON carb_intakes(timestamp DESC);
    CREATE INDEX idx_carbs_meal_type ON carb_intakes(meal_type);
    CREATE INDEX idx_carbs_patient_recent ON carb_intakes(patient_id, timestamp DESC);

    -- ============================================================================
    -- 4A. MEALS
    -- ============================================================================
    -- Meal is the aggregate root for user-entered carbohydrate capture.
    -- The meal owns up to 12 carbohydrate groups.
    --
    -- Step 1 lifecycle:
    --     captured
    --
    -- Later lifecycle states will be added for calculation, dose 1,
    -- dose 2, confirmation and actual intake.
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
            CHECK (status IN ('captured', 'active', 'completed')),

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
    -- A group represents one of the predefined carbohydrate groups.
    --
    -- group_number:
    --     1-11 = predefined groups
    --     12   = reserved for future Custom implementation
    --
    -- carb_factor_g_per_g is stored as an event snapshot.
    -- Therefore historical meals remain reproducible if a food definition
    -- changes later.
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
-- Immutable snapshot of the inputs and therapy rules used to calculate a
-- meal recommendation. This is deliberately separate from Dose 1 / Dose 2.
CREATE TABLE meal_calculations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_id UUID NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,

    calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Glucose state at calculation time
    glucose_mg_dl DECIMAL(6, 2),
    target_glucose_mg_dl DECIMAL(6, 2),

    -- Therapy-rule snapshot
    carb_factor_g_per_unit DECIMAL(8, 3),
    insulin_sensitivity_mg_dl_per_unit DECIMAL(8, 2),

    -- Meal input snapshot
    carbohydrate_total_grams DECIMAL(7, 1) NOT NULL,

    -- Calculation components
    carbohydrate_dose_units DECIMAL(8, 2),
    correction_dose_units DECIMAL(8, 2),
    calculated_dose_units DECIMAL(8, 2),

    -- Calculation provenance
    calculation_version VARCHAR(50) NOT NULL DEFAULT '1',
    notes TEXT
);

CREATE INDEX idx_meal_calculations_meal
    ON meal_calculations(meal_id, calculated_at DESC);
CREATE INDEX idx_meal_calculations_patient
    ON meal_calculations(patient_id, calculated_at DESC);

-- ============================================================================
    -- 6. ACTIVITIES
    -- ============================================================================
    CREATE TABLE activities (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        activity_type VARCHAR(100) NOT NULL,
        intensity VARCHAR(50),
        duration_minutes INTEGER NOT NULL,
        calories_burned INTEGER,
        heart_rate_avg INTEGER,
        heart_rate_max INTEGER,
        timestamp TIMESTAMP NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source VARCHAR(50),
        device_name VARCHAR(100),
        notes TEXT
    );
    CREATE INDEX idx_activity_patient_time ON activities(patient_id, timestamp DESC);
    CREATE INDEX idx_activity_timestamp ON activities(timestamp DESC);
    CREATE INDEX idx_activity_type ON activities(activity_type);
    CREATE INDEX idx_activity_patient_recent ON activities(patient_id, timestamp DESC);

    -- ============================================================================
    -- 7. HORMONAL_CONTEXTS (UPDATED: User-provided vs. learned distinction)
    -- ============================================================================
    CREATE TABLE hormonal_contexts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        context_type VARCHAR(100) NOT NULL, -- 'stress' | 'sleep_quality' | 'menstrual_cycle' | 'illness' | 'medication_change'
        context_value VARCHAR(255),
        numerical_value DECIMAL(10, 2),
        timestamp TIMESTAMP NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        -- ADDED: Source distinction
        is_user_provided BOOLEAN DEFAULT FALSE,
        confidence_score DECIMAL(5, 2), -- Only for learned/detected entries (0-1)
        source_type VARCHAR(50), -- 'manual' | 'learned_from_glucose' | 'inferred_from_activity' | 'api'
        intensity_level VARCHAR(50),
        duration_minutes INTEGER,
        notes TEXT
    );
    CREATE INDEX idx_hormonal_patient_time ON hormonal_contexts(patient_id, timestamp DESC);
    CREATE INDEX idx_hormonal_type ON hormonal_contexts(context_type);
    CREATE INDEX idx_hormonal_timestamp ON hormonal_contexts(timestamp DESC);
    CREATE INDEX idx_hormonal_patient_day ON hormonal_contexts(patient_id, DATE(timestamp) DESC);

    -- ============================================================================
    -- 8. THERAPY_LIMITS
    -- ============================================================================
    CREATE TABLE therapy_limits (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        limit_type VARCHAR(100) NOT NULL,
        lower_bound DECIMAL(10, 2),
        upper_bound DECIMAL(10, 2),
        is_hard_limit BOOLEAN DEFAULT FALSE,
        time_of_day_start TIME,
        time_of_day_end TIME,
        day_of_week INTEGER, -- 0=Sunday, 6=Saturday (NULL = all days)
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    );
    CREATE INDEX idx_therapy_patient ON therapy_limits(patient_id);
    CREATE INDEX idx_therapy_type ON therapy_limits(limit_type);
    CREATE INDEX idx_therapy_limits_tod ON therapy_limits(patient_id, time_of_day_start, day_of_week);

    -- ============================================================================
    -- 9. USER_SETTINGS (UPDATED: Safety bias and model selection)
    -- ============================================================================
    CREATE TABLE user_settings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL UNIQUE REFERENCES patients(id) ON DELETE CASCADE,
        -- Unit preferences
        glucose_unit_preference VARCHAR(20) DEFAULT 'mg/dl',
        carb_unit_preference VARCHAR(20) DEFAULT 'grams',
        insulin_unit_preference VARCHAR(20) DEFAULT 'units',
        -- Notification settings
        notification_enabled BOOLEAN DEFAULT TRUE,
        notification_low_threshold_mg_dl DECIMAL(6, 2),
        notification_high_threshold_mg_dl DECIMAL(6, 2),
        -- Forecast configuration
        forecast_horizon_minutes INTEGER DEFAULT 360,
        -- ADDED: Model and safety configuration
        safety_bias VARCHAR(20) DEFAULT 'balanced', -- 'conservative' | 'balanced' | 'aggressive'
        selected_model VARCHAR(50) DEFAULT 'ensemble', -- 'ARIMA' | 'IOB' | 'LSTM' | 'ensemble'
        ensemble_model_weights JSONB, -- e.g., {"ARIMA": 0.25, "IOB": 0.25, "LSTM": 0.5}
        override_sensitivity_factor DECIMAL(5, 2) DEFAULT 1.0, -- ISF/ICR multiplier
        carb_absorption_profile VARCHAR(50) DEFAULT 'standard', -- 'fast' | 'standard' | 'slow'
        -- Display and privacy
        language_preference VARCHAR(20) DEFAULT 'en',
        display_theme VARCHAR(50) DEFAULT 'light',
        data_sharing_consent BOOLEAN DEFAULT FALSE,
        research_participation BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_settings_patient ON user_settings(patient_id);

    -- ============================================================================
    -- 10. TIME_OF_DAY_PROFILES
    -- ============================================================================
    CREATE TABLE time_of_day_profiles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        profile_name VARCHAR(100),
        time_period_start TIME NOT NULL,
        time_period_end TIME NOT NULL,
        insulin_sensitivity_mg_dl_per_unit DECIMAL(8, 2),
        insulin_to_carb_ratio DECIMAL(8, 2),
        target_glucose_min_mg_dl DECIMAL(6, 2),
        target_glucose_max_mg_dl DECIMAL(6, 2),
        day_of_week INTEGER, -- 0=Sunday, 6=Saturday (NULL = all days)
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    CREATE INDEX idx_profile_patient ON time_of_day_profiles(patient_id);
    CREATE INDEX idx_profile_time ON time_of_day_profiles(time_period_start, time_period_end);

    -- ============================================================================
    -- 11. FORECAST_RESULTS (UPDATED: Threshold crossing indicators)
    -- ============================================================================
    CREATE TABLE forecast_results (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        model_version VARCHAR(100) NOT NULL,
        forecast_generated_at TIMESTAMP NOT NULL,
        forecast_horizon_minutes INTEGER NOT NULL,
        input_glucose_mg_dl DECIMAL(6, 2),
        -- Point forecast (primary prediction at horizon end or aggregated)
        predicted_glucose_mg_dl DECIMAL(6, 2),
        prediction_timestamp TIMESTAMP NOT NULL,
        lower_confidence_bound_mg_dl DECIMAL(6, 2),
        upper_confidence_bound_mg_dl DECIMAL(6, 2),
        confidence_level DECIMAL(5, 2),
        -- Accuracy metrics (updated when actual values available)
        prediction_error_mg_dl DECIMAL(8, 2),
        is_in_range BOOLEAN,
        forecast_quality_score DECIMAL(5, 2),
        -- ADDED: Threshold crossing indicators (decision support)
        will_cross_70_mg_dl BOOLEAN DEFAULT FALSE,
        will_cross_54_mg_dl BOOLEAN DEFAULT FALSE,
        will_cross_180_mg_dl BOOLEAN DEFAULT FALSE,
        time_to_70_minutes INTEGER,
        time_to_54_minutes INTEGER,
        needs_intervention BOOLEAN DEFAULT FALSE,
        intervention_type VARCHAR(50), -- 'fast_carbs' | 'reduce_basal' | 'none'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    CREATE INDEX idx_forecast_patient_time ON forecast_results(patient_id, prediction_timestamp DESC);
    CREATE INDEX idx_forecast_generated_at ON forecast_results(forecast_generated_at DESC);
    CREATE INDEX idx_forecast_model ON forecast_results(model_version);
    -- ADDED: Conditional indexes for decision support
    CREATE INDEX idx_forecast_needs_intervention ON forecast_results(patient_id, forecast_generated_at DESC)
        WHERE needs_intervention = TRUE;
    CREATE INDEX idx_forecast_threshold_70 ON forecast_results(patient_id, forecast_generated_at DESC)
        WHERE will_cross_70_mg_dl = TRUE;
    CREATE INDEX idx_forecast_threshold_54 ON forecast_results(patient_id, forecast_generated_at DESC)
        WHERE will_cross_54_mg_dl = TRUE;

    -- ============================================================================
    -- 11b. FORECAST_PREDICTIONS (NEW: Separate table for 72-point trajectories)
    -- ============================================================================
    CREATE TABLE forecast_predictions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        forecast_result_id UUID NOT NULL REFERENCES forecast_results(id) ON DELETE CASCADE,
        prediction_point_index INTEGER NOT NULL, -- 0-71 (0 = now, 71 = 6hrs future)
        time_offset_minutes INTEGER NOT NULL, -- 0, 5, 10, ..., 360
        prediction_timestamp TIMESTAMP NOT NULL,
        predicted_glucose_mg_dl DECIMAL(6, 2) NOT NULL,
        lower_bound_mg_dl DECIMAL(6, 2),
        upper_bound_mg_dl DECIMAL(6, 2),
        confidence_level DECIMAL(5, 2),
        -- Threshold crossings
        crosses_threshold_70 BOOLEAN DEFAULT FALSE,
        crosses_threshold_54 BOOLEAN DEFAULT FALSE,
        crosses_threshold_180 BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(forecast_result_id, prediction_point_index)
    );
    CREATE INDEX idx_predictions_forecast ON forecast_predictions(forecast_result_id);
    CREATE INDEX idx_predictions_timestamp ON forecast_predictions(prediction_timestamp DESC);
    -- ADDED: Conditional indexes for threshold queries
    CREATE INDEX idx_predictions_threshold_70 ON forecast_predictions(forecast_result_id, prediction_timestamp DESC)
        WHERE crosses_threshold_70 = TRUE;
    CREATE INDEX idx_predictions_threshold_54 ON forecast_predictions(forecast_result_id, prediction_timestamp DESC)
        WHERE crosses_threshold_54 = TRUE;

    -- ============================================================================
    -- 12. MODEL_TRAINING_LOGS (UPDATED: R², safety metrics, validation gate)
    -- ============================================================================
    CREATE TABLE model_training_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        model_version VARCHAR(100) NOT NULL UNIQUE,
        model_type VARCHAR(100),
        training_start_time TIMESTAMP NOT NULL,
        training_end_time TIMESTAMP,
        training_duration_seconds INTEGER,
        patient_id UUID REFERENCES patients(id) ON DELETE SET NULL,
        training_data_records INTEGER,
        training_samples_count INTEGER,
        training_data_start_date DATE,
        training_data_end_date DATE,
        -- Core metrics
        training_loss DECIMAL(15, 6),
        validation_loss DECIMAL(15, 6),
        test_loss DECIMAL(15, 6),
        mae_mg_dl DECIMAL(8, 2),
        rmse_mg_dl DECIMAL(8, 2),
        mape_percent DECIMAL(8, 2),
        -- ADDED: R² validation metric
        r_squared_score DECIMAL(8, 4),
        -- ADDED: Safety-specific metrics
        hypoglycemia_prediction_precision DECIMAL(5, 2),
        hypoglycemia_prediction_recall DECIMAL(5, 2),
        hyperglycemia_prediction_precision DECIMAL(5, 2),
        hyperglycemia_prediction_recall DECIMAL(5, 2),
        false_alarm_rate DECIMAL(5, 2), -- False hypo alerts per day
        missed_hypo_rate DECIMAL(5, 2), -- Missed hypo predictions per day
        time_in_range_accuracy DECIMAL(5, 2),
        -- Original fields
        hypoglycemia_sensitivity DECIMAL(5, 2),
        hyperglycemia_sensitivity DECIMAL(5, 2),
        hyperparameters JSONB,
        training_status VARCHAR(50),
        -- ADDED: Validation gate
        model_passed_validation BOOLEAN DEFAULT FALSE,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_training_model_version ON model_training_logs(model_version);
    CREATE INDEX idx_training_start_time ON model_training_logs(training_start_time DESC);
    CREATE INDEX idx_training_status ON model_training_logs(training_status, created_at DESC);
    -- ADDED: Conditional index for production-ready models
    CREATE INDEX idx_training_passed ON model_training_logs(patient_id, created_at DESC)
        WHERE model_passed_validation = TRUE;

    -- ============================================================================
    -- 13. DATA_IMPORT_LOGS
    -- ============================================================================
    CREATE TABLE data_import_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        import_source VARCHAR(100) NOT NULL,
        device_type VARCHAR(100),
        file_name VARCHAR(255),
        import_start_time TIMESTAMP NOT NULL,
        import_end_time TIMESTAMP,
        import_duration_seconds INTEGER,
        total_records_imported INTEGER,
        glucose_records_count INTEGER,
        insulin_records_count INTEGER,
        carb_records_count INTEGER,
        activity_records_count INTEGER,
        import_status VARCHAR(50),
        error_message TEXT,
        warnings TEXT,
        data_quality_score DECIMAL(5, 2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_import_patient_time ON data_import_logs(patient_id, import_start_time DESC);
    CREATE INDEX idx_import_source ON data_import_logs(import_source);
    CREATE INDEX idx_import_status ON data_import_logs(import_status);
    CREATE INDEX idx_import_device_timestamp ON data_import_logs(patient_id, device_type, import_start_time DESC);

    -- ============================================================================
    -- UTILITY: Enable JSON support and create trigger for updated_at
    -- ============================================================================
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON patients
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_therapy_limits_updated_at BEFORE UPDATE ON therapy_limits
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_user_settings_updated_at BEFORE UPDATE ON user_settings
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_time_of_day_profiles_updated_at BEFORE UPDATE ON time_of_day_profiles
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_forecast_results_updated_at BEFORE UPDATE ON forecast_results
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    -- ============================================================================
    -- UTILITY: Computed column helper (pump_last_sync_ago_minutes)
    -- ============================================================================
    CREATE OR REPLACE FUNCTION update_pump_sync_ago()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.last_pump_sync IS NOT NULL THEN
            NEW.pump_last_sync_ago_minutes := EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - NEW.last_pump_sync)) / 60;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER update_patients_pump_sync BEFORE UPDATE ON patients
        FOR EACH ROW EXECUTE FUNCTION update_pump_sync_ago();

    -- ============================================================================
    -- UTILITY: Auto-flag hypo/hyper on glucose insert
    -- ============================================================================
    CREATE OR REPLACE FUNCTION flag_glucose_thresholds()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.is_hypo := NEW.glucose_value_mg_dl < 70;
        NEW.is_severe_hypo := NEW.glucose_value_mg_dl < 54;
        NEW.is_hyper := NEW.glucose_value_mg_dl > 180;
        NEW.is_severe_hyper := NEW.glucose_value_mg_dl > 250;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER flag_glucose_thresholds_on_insert BEFORE INSERT ON glucose_readings
        FOR EACH ROW EXECUTE FUNCTION flag_glucose_thresholds();

    CREATE TRIGGER flag_glucose_thresholds_on_update BEFORE UPDATE ON glucose_readings
        FOR EACH ROW EXECUTE FUNCTION flag_glucose_thresholds();
