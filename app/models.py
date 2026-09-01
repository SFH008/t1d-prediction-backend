"""
SQLAlchemy ORM Models for T1D Glucose Forecasting System.
Matches the corrected PostgreSQL schema.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Date,
    DateTime,
    Time,
    Boolean,
    ForeignKey,
    Text,
    JSON,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base

from app.ml.layer1 import (
    TrainingDatasetBuilder,
    DataValidator,
    ChronologicalSplitter,
    CanonicalFeatures,
)

# builder = TrainingDatasetBuilder("postgresql://...")
# raw_df = builder.extract_patient_data(patient_id, start, end)

class Patient(Base):
    """Patient information and device status."""
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stable external identifier.
    # For Medtronic imports this is the device serial number.
    external_patient_id = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)

    date_of_birth = Column(Date)
    sex = Column(String(1))
    diabetes_type = Column(String(20), nullable=False, default="type_1")
    diagnosis_date = Column(Date)
    time_zone = Column(String(50), default="UTC")

    # Patient measurements
    weight_kg = Column(Numeric(5, 2))
    height_cm = Column(Numeric(5, 1))

    # Device tracking
    pump_status = Column(String(50), default="unknown")
    sensor_status = Column(String(50), default="unknown")
    pump_battery_percent = Column(Numeric(5, 2))
    sensor_battery_percent = Column(Numeric(5, 2))
    last_pump_sync = Column(DateTime)
    last_sensor_sync = Column(DateTime)
    pump_last_sync_ago_minutes = Column(Integer)

    # Medtronic device / CGM state
    device_serial_number = Column(String(255))
    device_model = Column(String(100))
    reservoir_remaining_units = Column(Numeric(8, 2))
    calibration_status = Column(String(100))
    sensor_duration_hours = Column(Numeric(8, 2))

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    glucose_readings = relationship(
        "GlucoseReading",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    insulin_events = relationship(
        "InsulinEvent",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    carb_intakes = relationship(
        "CarbIntake",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    activities = relationship(
        "Activity",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    hormonal_contexts = relationship(
        "HormonalContext",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    therapy_limits = relationship(
        "TherapyLimit",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    user_settings = relationship(
        "UserSettings",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan"
    )
    time_of_day_profiles = relationship(
        "TimeOfDayProfile",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    forecast_results = relationship(
        "ForecastResult",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    model_training_logs = relationship(
        "ModelTrainingLog",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    data_import_logs = relationship(
        "DataImportLog",
        back_populates="patient",
        cascade="all, delete-orphan"
    )


class GlucoseReading(Base):
    """Continuous glucose monitoring readings."""
    __tablename__ = "glucose_readings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    glucose_value_mg_dl = Column(Numeric(6, 2), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    reading_type = Column(String(50))  # 'cgm', 'meter', etc.
    source = Column(String(100))  # 'medtronic_export', etc.
    is_valid = Column(Boolean, default=True)

    # Auto-classified thresholds
    is_hypo = Column(Boolean, default=False, index=True)
    is_severe_hypo = Column(Boolean, default=False, index=True)
    is_hyper = Column(Boolean, default=False, index=True)
    is_severe_hyper = Column(Boolean, default=False, index=True)

    trend_arrow = Column(String(10))  # '↑', '↓', '→', etc.

    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="glucose_readings")

    # Unique constraint
    __table_args__ = (
        # Composite index for fast queries
        # (patient_id, timestamp) should be unique
    )


class InsulinEvent(Base):
    """Insulin delivery events (basal, bolus, etc.)."""
    __tablename__ = "insulin_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    insulin_type = Column(String(50), nullable=False)  # 'basal', 'bolus', 'rewind', etc.
    dose_units = Column(Numeric(8, 2), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    delivery_method = Column(String(50))  # 'pump', 'pen', 'manual'
    source = Column(String(100))  # 'medtronic_export', etc.

    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="insulin_events")


class CarbIntake(Base):
    """Carbohydrate intake records."""
    __tablename__ = "carb_intakes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id"),
        nullable=False,
        index=True
    )
    carbs_grams = Column(Numeric(6, 1), nullable=False)
    food_description = Column(Text)
    food_category = Column(String(100))
    meal_type = Column(String(50))
    confidence_level = Column(String(20))

    timestamp = Column(DateTime, nullable=False, index=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50))
    is_estimated = Column(Boolean, default=False)
    notes = Column(Text)

    patient = relationship("Patient", back_populates="carb_intakes")


class Activity(Base):
    """Physical activity and exercise records."""
    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    activity_type = Column(String(100))  # 'running', 'cycling', 'walking', etc.
    intensity = Column(String(50))  # 'light', 'moderate', 'vigorous'
    duration_minutes = Column(Integer)
    heart_rate_avg = Column(Integer)
    heart_rate_max = Column(Integer)
    calories_burned = Column(Numeric(8, 2))
    timestamp = Column(DateTime, nullable=False, index=True)
    source = Column(String(100), default="manual")  # 'manual', 'wear_os', 'fitbit', etc.

    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="activities")


class HormonalContext(Base):
    """Hormonal and contextual factors (stress, sleep, menstrual cycle, etc.)."""
    __tablename__ = "hormonal_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    context_type = Column(String(100), nullable=False)  # 'stress', 'sleep_quality', 'menstrual_cycle', etc.
    context_value = Column(String(255))
    numerical_value = Column(Numeric(10, 2))
    timestamp = Column(DateTime, nullable=False, index=True)
    is_user_provided = Column(Boolean, default=False)  # User input vs. learned
    confidence_score = Column(Numeric(5, 2))  # For learned entries (0-1)
    source_type = Column(String(50))  # 'manual', 'learned_from_glucose', etc.
    intensity_level = Column(String(50))
    duration_minutes = Column(Integer)

    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="hormonal_contexts")


class TherapyLimit(Base):
    """Therapy target glucose ranges."""
    __tablename__ = "therapy_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    limit_type = Column(String(100), nullable=False)  # 'glucose_target', etc.
    lower_bound = Column(Numeric(10, 2), nullable=False)
    upper_bound = Column(Numeric(10, 2), nullable=False)
    is_hard_limit = Column(Boolean, default=False)
    time_of_day_start = Column(Time)  # HH:MM format
    time_of_day_end = Column(Time)    # HH:MM format
    day_of_week = Column(Integer)  # 0=Sun, 6=Sat, NULL=all days
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="therapy_limits")


class UserSettings(Base):
    """User-configurable settings."""
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), unique=True, nullable=False)

    # Unit preferences
    glucose_unit_preference = Column(String(20), default="mg/dl")
    carb_unit_preference = Column(String(20), default="grams")
    insulin_unit_preference = Column(String(20), default="units")

    # Notifications
    notification_enabled = Column(Boolean, default=True)
    notification_low_threshold_mg_dl = Column(Numeric(6, 2), default=70)
    notification_high_threshold_mg_dl = Column(Numeric(6, 2), default=180)

    # Forecast
    forecast_horizon_minutes = Column(Integer, default=360)

    # Safety & Model
    safety_bias = Column(String(20), default="balanced")  # 'conservative', 'balanced', 'aggressive'
    selected_model = Column(String(50), default="ensemble")
    ensemble_model_weights = Column(JSON)  # e.g., {"ARIMA": 0.25, "LSTM": 0.75}
    override_sensitivity_factor = Column(Numeric(5, 2))  # ISF/ICR multiplier
    carb_absorption_profile = Column(String(50))  # 'fast', 'standard', 'slow'

    # Display & Privacy
    language_preference = Column(String(20), default="en")
    display_theme = Column(String(50), default="light")
    data_sharing_consent = Column(Boolean, default=False)
    research_participation = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="user_settings")


class TimeOfDayProfile(Base):
    """Time-of-day insulin sensitivity and carb ratio profiles."""
    __tablename__ = "time_of_day_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    profile_name = Column(String(100))
    time_period_start = Column(String(5), nullable=False)  # HH:MM
    time_period_end = Column(String(5), nullable=False)    # HH:MM
    insulin_sensitivity_mg_dl_per_unit = Column(Numeric(8, 2), nullable=False)
    insulin_to_carb_ratio = Column(Numeric(8, 2), nullable=False)
    target_glucose_min_mg_dl = Column(Numeric(6, 2))
    target_glucose_max_mg_dl = Column(Numeric(6, 2))
    day_of_week = Column(Integer)  # 0=Sun, 6=Sat, NULL=all days
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="time_of_day_profiles")


class ForecastResult(Base):
    """Glucose forecast results."""
    __tablename__ = "forecast_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    model_version = Column(String(100))
    forecast_generated_at = Column(DateTime, default=datetime.utcnow)
    forecast_horizon_minutes = Column(Integer, default=360)

    # Forecast values
    predicted_glucose_mg_dl = Column(Numeric(6, 2))
    lower_confidence_bound_mg_dl = Column(Numeric(6, 2))
    upper_confidence_bound_mg_dl = Column(Numeric(6, 2))
    confidence_level = Column(Numeric(5, 2))

    # Threshold crossing
    will_cross_70_mg_dl = Column(Boolean, default=False)
    will_cross_54_mg_dl = Column(Boolean, default=False)
    will_cross_180_mg_dl = Column(Boolean, default=False)
    time_to_70_minutes = Column(Integer)
    time_to_54_minutes = Column(Integer)

    # Decision support
    needs_intervention = Column(Boolean, default=False)
    intervention_type = Column(String(50))  # 'fast_carbs', 'reduce_basal', 'none'

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="forecast_results")


class ForecastPrediction(Base):
    """Individual forecast prediction points (one per 5 minutes, 72 total)."""
    __tablename__ = "forecast_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_result_id = Column(UUID(as_uuid=True), ForeignKey("forecast_results.id"), nullable=False, index=True)
    prediction_point_index = Column(Integer, nullable=False)  # 0-71
    time_offset_minutes = Column(Integer, nullable=False)  # 0, 5, 10, ..., 360
    prediction_timestamp = Column(DateTime, nullable=False)
    predicted_glucose_mg_dl = Column(Numeric(6, 2), nullable=False)
    lower_bound_mg_dl = Column(Numeric(6, 2))
    upper_bound_mg_dl = Column(Numeric(6, 2))
    confidence_level = Column(Numeric(5, 2))
    crosses_threshold_70 = Column(Boolean, default=False)
    crosses_threshold_54 = Column(Boolean, default=False)
    crosses_threshold_180 = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class ModelTrainingLog(Base):
    """Model training metadata and performance metrics."""
    __tablename__ = "model_training_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version = Column(String(100), unique=True, nullable=False)
    model_type = Column(String(100))  # 'ARIMA', 'IOB', 'LSTM', 'ensemble'
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)

    # Training metadata
    training_start_time = Column(DateTime)
    training_end_time = Column(DateTime)
    training_duration_seconds = Column(Integer)
    training_data_records = Column(Integer)
    training_samples_count = Column(Integer)
    training_data_start_date = Column(DateTime)
    training_data_end_date = Column(DateTime)

    # Metrics
    training_loss = Column(Numeric(15, 6))
    validation_loss = Column(Numeric(15, 6))
    test_loss = Column(Numeric(15, 6))
    mae_mg_dl = Column(Numeric(8, 2))
    rmse_mg_dl = Column(Numeric(8, 2))
    mape_percent = Column(Numeric(8, 2))
    r_squared_score = Column(Numeric(8, 4))

    # Safety metrics
    hypoglycemia_prediction_precision = Column(Numeric(5, 2))
    hypoglycemia_prediction_recall = Column(Numeric(5, 2))
    hyperglycemia_prediction_precision = Column(Numeric(5, 2))
    hyperglycemia_prediction_recall = Column(Numeric(5, 2))
    false_alarm_rate = Column(Numeric(5, 2))  # Per day
    missed_hypo_rate = Column(Numeric(5, 2))  # Per day
    time_in_range_accuracy = Column(Numeric(5, 2))

    # Validation
    model_passed_validation = Column(Boolean, default=False)

    hyperparameters = Column(JSON)
    training_status = Column(String(50))  # 'pending', 'running', 'completed', 'failed'
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="model_training_logs")


class DataImportLog(Base):
    """Data import tracking."""
    __tablename__ = "data_import_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    import_source = Column(String(100), nullable=False)  # 'medtronic_minimed', etc.
    device_type = Column(String(100))
    file_name = Column(String(255))

    import_start_time = Column(DateTime, default=datetime.utcnow)
    import_end_time = Column(DateTime)
    import_duration_seconds = Column(Integer)

    # Counts
    total_records_imported = Column(Integer)
    glucose_records_count = Column(Integer)
    insulin_records_count = Column(Integer)
    carb_records_count = Column(Integer)
    activity_records_count = Column(Integer)

    # Status
    import_status = Column(String(50))  # 'PENDING', 'SUCCESS', 'FAILED'
    error_message = Column(Text)
    warnings = Column(Text)
    data_quality_score = Column(Numeric(5, 2))  # 0-100%

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="data_import_logs")
