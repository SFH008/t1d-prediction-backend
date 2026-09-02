"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# ============================================================================
# Patient Schemas
# ============================================================================

class PatientBase(BaseModel):
    """Base patient schema."""
    first_name: str
    last_name: str
    diabetes_type: str = "type_1"
    time_zone: str = "UTC"


class PatientCreate(PatientBase):
    """Schema for creating new patient."""
    external_patient_id: str


class PatientUpdate(BaseModel):
    """Schema for updating patient."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    time_zone: Optional[str] = None
    is_active: Optional[bool] = None


class PatientResponse(PatientBase):
    """Schema for patient response."""
    id: UUID
    external_patient_id: str

    # Pump / CGM device information
    device_serial_number: Optional[str] = None
    device_model: Optional[str] = None
    reservoir_remaining_units: Optional[float] = None
    sensor_state: Optional[str] = None
    calibration_status: Optional[str] = None
    sensor_duration_hours: Optional[float] = None

    # Current device status
    pump_status: Optional[str] = None
    sensor_status: Optional[str] = None
    pump_battery_percent: Optional[float] = None
    sensor_battery_percent: Optional[float] = None
    last_pump_sync: Optional[datetime] = None
    last_sensor_sync: Optional[datetime] = None

    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============================================================================
# Glucose Schemas
# ============================================================================

class GlucoseReadingBase(BaseModel):
    """Base glucose reading schema."""
    glucose_value_mg_dl: float = Field(..., ge=40, le=400)
    timestamp: datetime
    reading_type: str = "cgm"
    source: str = "app"


class GlucoseReadingCreate(GlucoseReadingBase):
    """Schema for creating glucose reading."""
    pass


class GlucoseReadingResponse(GlucoseReadingBase):
    """Schema for glucose reading response."""
    id: UUID
    patient_id: UUID
    is_hypo: bool
    is_severe_hypo: bool
    is_hyper: bool
    is_severe_hyper: bool
    sensor_state: Optional[str]
    trend_arrow: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


class GlucoseStats(BaseModel):
    """Glucose statistics summary."""
    total_readings: int
    avg_glucose: float
    min_glucose: float
    max_glucose: float
    hypo_count: int
    severe_hypo_count: int
    hyper_count: int
    severe_hyper_count: int
    time_in_range_percent: float


# ============================================================================
# Insulin Schemas
# ============================================================================

class InsulinEventBase(BaseModel):
    """Base insulin event schema."""
    insulin_type: str
    dose_units: float = Field(..., ge=0, le=100)
    timestamp: datetime
    delivery_method: str = "pump"


class InsulinEventCreate(InsulinEventBase):
    """Schema for creating insulin event."""
    pass


class InsulinEventResponse(InsulinEventBase):
    """Schema for insulin event response."""
    id: UUID
    patient_id: UUID
    source: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Therapy Limit Schemas
# ============================================================================

class TherapyLimitBase(BaseModel):
    """Base therapy limit schema."""
    limit_type: str
    lower_bound: float
    upper_bound: float
    is_hard_limit: bool = False


class TherapyLimitCreate(TherapyLimitBase):
    """Schema for creating therapy limit."""
    time_of_day_start: Optional[str] = None
    time_of_day_end: Optional[str] = None
    day_of_week: Optional[int] = None


class TherapyLimitResponse(TherapyLimitBase):
    """Schema for therapy limit response."""
    id: UUID
    patient_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Import Schemas
# ============================================================================

class DataImportResponse(BaseModel):
    """Schema for data import response."""
    id: UUID
    patient_id: UUID
    import_source: str
    file_name: str
    import_status: str
    glucose_records_count: int
    insulin_records_count: int
    import_start_time: datetime
    import_end_time: Optional[datetime]
    data_quality_score: Optional[float]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class ImportStatusResponse(BaseModel):
    """Schema for import status response."""
    import_id: UUID
    status: str  # 'PENDING', 'PROCESSING', 'SUCCESS', 'FAILED'
    patient_id: UUID
    glucose_count: int
    insulin_count: int
    error_message: Optional[str] = None


# ============================================================================
# Forecast Schemas
# ============================================================================

class ForecastPredictionResponse(BaseModel):
    """Single forecast prediction point."""
    time_offset_minutes: int
    prediction_timestamp: datetime
    predicted_glucose_mg_dl: float
    lower_bound_mg_dl: Optional[float]
    upper_bound_mg_dl: Optional[float]
    confidence_level: Optional[float]


class ForecastResultResponse(BaseModel):
    """Forecast result with all prediction points."""
    id: UUID
    patient_id: UUID
    forecast_generated_at: datetime
    forecast_horizon_minutes: int
    predicted_glucose_mg_dl: float
    confidence_level: Optional[float]
    will_cross_70_mg_dl: bool
    will_cross_54_mg_dl: bool
    will_cross_180_mg_dl: bool
    time_to_70_minutes: Optional[int]
    time_to_54_minutes: Optional[int]
    needs_intervention: bool
    intervention_type: Optional[str]
    predictions: List[ForecastPredictionResponse]

    class Config:
        from_attributes = True


# ============================================================================
# Meal / Carb Capture Schemas
# ============================================================================

class MealCarbGroupCreate(BaseModel):
    """
    One carbohydrate group submitted as part of a meal.

    The client supplies only the canonical group number and
    food quantity. Group metadata and carb conversion factor
    are resolved by the backend.
    """

    model_config = ConfigDict(extra="forbid")

    group_number: int = Field(..., ge=1, le=12)
    quantity_grams: float = Field(..., gt=0, le=5000)


class MealCarbGroupResponse(BaseModel):
    id: UUID
    group_number: int
    group_key: str
    group_name: str
    quantity_grams: float
    carb_factor_g_per_g: float
    carbs_grams: float
    created_at: datetime

    class Config:
        from_attributes = True


class MealCreate(BaseModel):
    """
    Create a complete meal.

    The meal is the primary interaction. Carb groups are submitted together
    as one atomic request.
    """
    meal_timestamp: datetime
    meal_category: str = Field(..., min_length=1, max_length=50)
    carb_groups: List[MealCarbGroupCreate] = Field(
        ..., min_length=1, max_length=12
    )
    source: Optional[str] = "manual"
    notes: Optional[str] = None


class MealCarbGroupResponse(MealCarbGroupCreate):
    id: UUID
    carbs_grams: float

    class Config:
        from_attributes = True


class MealResponse(BaseModel):
    id: UUID
    patient_id: UUID
    meal_timestamp: datetime
    meal_category: str
    status: str
    total_carbs_grams: float
    source: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    carb_groups: List[MealCarbGroupResponse]

    class Config:
        from_attributes = True


# ============================================================================
# ============================================================================
# Carb Intake Schemas
# ============================================================================

class CarbIntakeCreate(BaseModel):
    """Schema for creating carb entry."""
    carbs_grams: float = Field(..., ge=0, le=500)
    food_description: str
    food_category: Optional[str] = None
    meal_type: str  # 'breakfast', 'lunch', 'dinner', 'snack'
    timestamp: datetime
    source: Optional[str] = "manual"
    is_estimated: Optional[bool] = False
    confidence_level: Optional[str] = None


class CarbIntakeResponse(CarbIntakeCreate):
    """Schema for carb entry response."""
    id: UUID
    patient_id: UUID
    recorded_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Meal Calculation Schemas
# ============================================================================

class MealCalculationCreate(BaseModel):
    """Client inputs for calculation version 3."""
    glucose_mg_dl: Optional[float] = Field(None, ge=20, le=600)
    manual_insulin_given_units: Optional[float] = Field(None, ge=0, le=100)


class MealCalculationResponse(BaseModel):
    """Calculation result and immutable therapy/strategy snapshot."""
    id: UUID
    meal_id: UUID
    patient_id: UUID
    calculated_at: datetime

    glucose_mg_dl: Optional[float]
    target_glucose_mg_dl: Optional[float]
    carb_factor_g_per_unit: Optional[float]
    insulin_sensitivity_mg_dl_per_unit: Optional[float]

    carbohydrate_total_grams: float
    carbohydrate_dose_units: Optional[float]
    correction_dose_units: Optional[float]
    calculated_dose_units: Optional[float]

    meal_therapy_profile_id: Optional[UUID] = None
    meal_basal_drift_mg_dl_per_hour: Optional[float] = None

    base_carbohydrate_grams: Optional[float] = None
    fat_protein_addon_percent: Optional[float] = None
    fat_protein_addon_grams: Optional[float] = None
    effective_carbohydrate_grams: Optional[float] = None

    absorption_profile_id: Optional[UUID] = None
    absorption_profile_key: Optional[str] = None
    absorption_duration_minutes: Optional[int] = None
    absorption_delay_minutes: Optional[int] = None
    absorption_classification_source: Optional[str] = None

    dose_1_share_percent: Optional[float] = None
    dose_2_share_percent: Optional[float] = None
    dose_2_delay_minutes: Optional[int] = None
    dose_2_timestamp: Optional[datetime] = None
    insulin_rounding_increment_units: Optional[float] = None
    strategy_source: Optional[str] = None
    strategy_version: Optional[str] = None

    dose_2_therapy_profile_id: Optional[UUID] = None
    dose_2_carb_factor_g_per_unit: Optional[float] = None
    dose_2_insulin_sensitivity_mg_dl_per_unit: Optional[float] = None
    dose_2_target_glucose_mg_dl: Optional[float] = None
    dose_2_basal_drift_mg_dl_per_hour: Optional[float] = None

    dose_1_carbohydrate_grams: Optional[float] = None
    dose_2_carbohydrate_grams: Optional[float] = None
    dose_1_carbohydrate_units: Optional[float] = None
    dose_1_units: Optional[float] = None
    dose_2_carbohydrate_units: Optional[float] = None
    dose_2_units: Optional[float] = None
    total_planned_dose_units: Optional[float] = None
    manual_insulin_given_units: Optional[float] = None

    calculation_version: str
    notes: Optional[str]

    class Config:
        from_attributes = True


# ============================================================================
# Frontend Meal Plan Read Schemas
# ============================================================================

class MealPlanMealResponse(BaseModel):
    """Meal metadata needed by the frontend plan screen."""
    id: UUID
    patient_id: UUID
    meal_timestamp: datetime
    meal_category: str
    total_carbs_grams: float
    absorption_profile_key: Optional[str] = None
    absorption_classification_source: Optional[str] = None


class MealPlanCalculationResponse(BaseModel):
    """Calculation fields that explain the split-dose plan."""
    id: UUID
    calculation_version: str
    calculated_at: datetime

    glucose_mg_dl: Optional[float] = None
    target_glucose_mg_dl: Optional[float] = None
    meal_icr_g_per_unit: Optional[float] = None
    meal_isf_mg_dl_per_unit: Optional[float] = None
    meal_basal_drift_mg_dl_per_hour: Optional[float] = None

    dose_2_icr_g_per_unit: Optional[float] = None
    dose_2_isf_mg_dl_per_unit: Optional[float] = None
    dose_2_basal_drift_mg_dl_per_hour: Optional[float] = None

    dose_1_share_percent: Optional[float] = None
    dose_2_share_percent: Optional[float] = None
    dose_2_delay_minutes: Optional[int] = None
    dose_2_timestamp: Optional[datetime] = None

    dose_1_units: Optional[float] = None
    dose_2_units: Optional[float] = None
    total_planned_dose_units: Optional[float] = None

    strategy_source: Optional[str] = None
    strategy_version: Optional[str] = None


class MealPlanAbsorptionResponse(BaseModel):
    """Absorption assumptions snapshotted into the calculation."""
    profile_key: Optional[str] = None
    duration_minutes: Optional[int] = None
    delay_minutes: Optional[int] = None
    classification_source: Optional[str] = None


# ============================================================================
# Multi-Dose Tracker Schemas
# ============================================================================

class MealDoseEventResponse(BaseModel):
    """Planned and actual state for one component of a split-dose plan."""
    id: UUID
    patient_id: UUID
    meal_id: UUID
    calculation_id: UUID
    dose_number: int

    planned_timestamp: datetime
    planned_units: float

    actual_timestamp: Optional[datetime] = None
    actual_units: Optional[float] = None
    status: str

    adjustment_reason: Optional[str] = None
    notes: Optional[str] = None
    insulin_event_id: Optional[UUID] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MealPlanResponse(BaseModel):
    """Consolidated immutable plan read model for React."""
    meal: MealPlanMealResponse
    calculation: MealPlanCalculationResponse
    absorption: MealPlanAbsorptionResponse
    dose_events: List[MealDoseEventResponse]


class MealDoseEventConfirm(BaseModel):
    """Confirm that a planned dose was administered as planned."""
    actual_units: float = Field(..., gt=0, le=100)
    actual_timestamp: datetime
    delivery_method: Optional[str] = "pump"
    notes: Optional[str] = None


class MealDoseEventAdjust(BaseModel):
    """Record an administered dose that differs from the planned dose."""
    actual_units: float = Field(..., gt=0, le=100)
    actual_timestamp: datetime
    adjustment_reason: str = Field(..., min_length=1, max_length=100)
    delivery_method: Optional[str] = "pump"
    notes: Optional[str] = None


class MealDoseEventSkip(BaseModel):
    """Record that a planned dose was deliberately not administered."""
    adjustment_reason: str = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = None


# ============================================================================
# Activity Schemas
# ============================================================================

class ActivityCreate(BaseModel):
    """Schema for creating activity."""
    activity_type: str  # 'running', 'cycling', 'walking', 'swimming', etc.
    intensity: str  # 'light', 'moderate', 'vigorous'
    duration_minutes: int = Field(..., ge=1, le=1440)
    calories_burned: Optional[float] = None
    heart_rate_avg: Optional[int] = None
    heart_rate_max: Optional[int] = None
    timestamp: datetime
    source: Optional[str] = "manual"


class ActivityResponse(ActivityCreate):
    """Schema for activity response."""
    id: UUID
    patient_id: UUID
    recorded_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Hormonal Context Schemas
# ============================================================================

class HormonalContextCreate(BaseModel):
    """Schema for creating hormonal context."""
    context_type: str  # 'stress', 'sleep_quality', 'menstrual_cycle', 'illness', 'medication_change'
    context_value: str
    numerical_value: Optional[float] = Field(None, ge=0, le=100)
    timestamp: datetime
    is_user_provided: Optional[bool] = True
    confidence_level: Optional[float] = Field(None, ge=0, le=1)
    source_type: Optional[str] = None  # 'manual', 'learned_from_glucose'
    intensity_level: Optional[str] = None  # 'mild', 'moderate', 'severe'
    duration_minutes: Optional[int] = None


class HormonalContextResponse(HormonalContextCreate):
    """Schema for hormonal context response."""
    id: UUID
    patient_id: UUID
    recorded_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# User Settings Schemas
# ============================================================================

class UserSettingsUpdate(BaseModel):
    """Schema for updating user settings."""
    glucose_unit_preference: Optional[str] = None
    carb_unit_preference: Optional[str] = None
    insulin_unit_preference: Optional[str] = None
    notification_enabled: Optional[bool] = None
    notification_low_threshold_mg_dl: Optional[float] = None
    notification_high_threshold_mg_dl: Optional[float] = None
    forecast_horizon_minutes: Optional[int] = None
    safety_bias: Optional[str] = None  # 'conservative', 'balanced', 'aggressive'
    selected_model: Optional[str] = None  # 'arima', 'iob_cob', 'lstm', 'ensemble'
    override_sensitivity_factor: Optional[float] = None
    carb_absorption_profile: Optional[str] = None  # 'fast', 'standard', 'slow'
    language_preference: Optional[str] = None
    display_theme: Optional[str] = None  # 'light', 'dark'
    data_sharing_consent: Optional[bool] = None
    research_participation: Optional[bool] = None


class UserSettingsResponse(UserSettingsUpdate):
    """Schema for user settings response."""
    id: UUID
    patient_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Time-of-Day Profile Schemas
# ============================================================================

class TimeOfDayProfileCreate(BaseModel):
    """Schema for creating time-of-day profile."""
    profile_name: Optional[str] = None
    time_period_start: str = Field(..., pattern=r"^\d{2}:\d{2}$")  # HH:MM
    time_period_end: str = Field(..., pattern=r"^\d{2}:\d{2}$")    # HH:MM
    insulin_sensitivity_mg_dl_per_unit: float = Field(..., gt=0)  # ISF
    insulin_to_carb_ratio: float = Field(..., gt=0)  # ICR
    target_glucose_min_mg_dl: Optional[float] = None
    target_glucose_max_mg_dl: Optional[float] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6)  # 0=Sun, 6=Sat


class TimeOfDayProfileResponse(TimeOfDayProfileCreate):
    """Schema for time-of-day profile response."""
    id: UUID
    patient_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Health Check Schemas
# ============================================================================

class HealthCheckResponse(BaseModel):
    """API health check response."""
    status: str
    app_name: str
    app_version: str
    timestamp: datetime


class DatabaseHealthResponse(BaseModel):
    """Database health check response."""
    status: str  # 'healthy', 'unhealthy'
    database_url: str
    connection_time_ms: float
    timestamp: datetime