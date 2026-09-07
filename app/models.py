"""
SQLAlchemy ORM Models for T1D Glucose Forecasting System.
Matches the corrected PostgreSQL schema.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
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
    meal_calculations = relationship(
        "MealCalculation",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    meals = relationship(
        "Meal",
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
    dose_strategy_settings = relationship(
        "DoseStrategySettings",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan"
    )
    carb_absorption_profiles = relationship(
        "CarbAbsorptionProfile",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    meal_dose_events = relationship(
        "MealDoseEvent",
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
    dose_units = Column(Numeric(8, 3), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    delivery_method = Column(String(50))  # 'pump', 'pen', 'manual'
    source = Column(String(100))  # 'medtronic_export', etc.

    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    patient = relationship("Patient", back_populates="insulin_events")
    meal_dose_events = relationship(
        "MealDoseEvent",
        back_populates="insulin_event",
    )


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


class CarbGroupDefinition(Base):
    """
    System-admin managed carbohydrate group definition.

    carb_factor_g_per_g expresses how many grams of carbohydrate
    are contributed by one gram of food quantity.

    MealCarbGroup stores a snapshot of the values actually used
    when a meal is captured.
    """

    __tablename__ = "carb_group_definitions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    group_number = Column(
        Integer,
        nullable=False,
        unique=True,
    )

    group_key = Column(
        String(100),
        nullable=False,
        unique=True,
    )

    group_name = Column(
        String(255),
        nullable=False,
    )

    carb_factor_g_per_g = Column(
        Numeric(8, 5),
        nullable=False,
    )

    default_absorption_profile_key = Column(
        String(50),
        nullable=True,
    )

    # System/global default only. Patient-specific clinical configuration may
    # override this value. The resolved value is snapshotted into the meal.
    default_absorption_delay_minutes = Column(
        Integer,
        nullable=False,
        default=10,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "group_number BETWEEN 1 AND 12",
            name="ck_carb_group_definitions_group_number",
        ),
        CheckConstraint(
            "carb_factor_g_per_g >= 0 "
            "AND carb_factor_g_per_g <= 1",
            name="ck_carb_group_definitions_factor",
        ),
        CheckConstraint(
            "default_absorption_profile_key IS NULL "
            "OR default_absorption_profile_key IN "
            "('very_fast', 'fast', 'medium', 'slow')",
            name="ck_carb_group_definitions_absorption_profile",
        ),
        CheckConstraint(
            "default_absorption_delay_minutes >= 0",
            name="ck_carb_group_definitions_default_absorption_delay",
        ),
    )


class PatientCarbGroupSetting(Base):
    """Admin-managed patient-specific carbohydrate-group configuration."""

    __tablename__ = "patient_carb_group_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    carb_group_definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("carb_group_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # NULL means inherit the system/global default for this field.
    absorption_profile_key = Column(String(50), nullable=True)
    absorption_delay_minutes = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    patient = relationship("Patient")
    carb_group_definition = relationship("CarbGroupDefinition")

    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "carb_group_definition_id",
            name="uq_patient_carb_group_settings_patient_group",
        ),
        CheckConstraint(
            "absorption_profile_key IS NULL "
            "OR absorption_profile_key IN "
            "('very_fast', 'fast', 'medium', 'slow')",
            name="ck_patient_carb_group_settings_profile",
        ),
        CheckConstraint(
            "absorption_delay_minutes IS NULL "
            "OR absorption_delay_minutes >= 0",
            name="ck_patient_carb_group_settings_delay",
        ),
    )


class Meal(Base):
    """
    User-entered meal.

    Meal is the aggregate root for carbohydrate capture. Individual
    carbohydrate groups belong to a meal and are never standalone
    user interactions at this layer.

    Step 1 state:
        captured

    Later states will be introduced for:
        calculation -> dose_1 -> dose_2 -> confirmed -> actual
    """
    __tablename__ = "meals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id"),
        nullable=False,
        index=True
    )

    meal_timestamp = Column(DateTime, nullable=False, index=True)
    meal_category = Column(String(50), nullable=False)

    # Step 1 lifecycle state. Keep this explicit now so later stages can
    # extend the same meal aggregate without changing its identity.
    status = Column(String(30), nullable=False, default="captured")

    # Snapshot of the calculated total at capture time.
    total_carbs_grams = Column(Numeric(8, 1), nullable=False, default=0)

    fat_grams = Column(
    Numeric(8, 1),
    nullable=False,
    default=Decimal("0.0"),
    )

    protein_grams = Column(
    Numeric(8, 1),
    nullable=False,
    default=Decimal("0.0"),
    )

    # Meal-derived absorption classification. The profile link points to the
    # current patient configuration, while key/source preserve readable event
    # context. Calculation snapshots remain immutable even if profiles change.
    absorption_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("carb_absorption_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    absorption_profile_key = Column(String(50))
    absorption_classification_source = Column(String(50))
    fat_protein_addon_percent = Column(Numeric(5, 2))

    source = Column(String(50), nullable=False, default="manual")
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    patient = relationship("Patient", back_populates="meals")
    carb_groups = relationship(
        "MealCarbGroup",
        back_populates="meal",
        cascade="all, delete-orphan",
        order_by="MealCarbGroup.group_number"
    )
    absorption_profile = relationship("CarbAbsorptionProfile")
    calculations = relationship(
        "MealCalculation",
        back_populates="meal",
        cascade="all, delete-orphan",
    )
    dose_events = relationship(
        "MealDoseEvent",
        back_populates="meal",
        cascade="all, delete-orphan",
        order_by="MealDoseEvent.dose_number",
    )


class MealCarbGroup(Base):
    """
    One carbohydrate group within a meal.

    quantity_grams is the quantity of the food/group entered by the user.
    carb_factor_g_per_g expresses how many grams of carbohydrate are
    contributed by one gram of that food/group.

    Example:
        quantity_grams = 100
        carb_factor_g_per_g = 0.30
        carbs_grams = 30

    carb_factor_g_per_g is deliberately stored on the event. This preserves
    the exact factor used when the meal was captured even if the predefined
    food definition changes later.
    """
    __tablename__ = "meal_carb_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 1..12. Group 12 is reserved for future custom carbohydrate support.
    group_number = Column(Integer, nullable=False)
    group_key = Column(String(100), nullable=False)
    group_name = Column(String(255), nullable=False)

    quantity_grams = Column(Numeric(8, 1), nullable=False)
    carb_factor_g_per_g = Column(Numeric(8, 5), nullable=False)

    # Snapshot of quantity * carb factor.
    carbs_grams = Column(Numeric(8, 1), nullable=False)

    consumed_quantity_grams = Column(
        Numeric(8, 1),
        nullable=True,
    )

    consumed_carbs_grams = Column(
        Numeric(8, 1),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    meal = relationship("Meal", back_populates="carb_groups")

    __table_args__ = (
        UniqueConstraint(
            "meal_id",
            "group_number",
            name="uq_meal_carb_group_number"
        ),
    )


class MealComponentAbsorption(Base):
    """
    Immutable absorption assumptions for one meal carbohydrate component.

    The row snapshots the patient-specific absorption profile and deterministic
    curve configuration used for this meal component.
    """

    __tablename__ = "meal_component_absorptions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    meal_carb_group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meal_carb_groups.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    absorption_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("carb_absorption_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    absorption_profile_key = Column(
        String(50),
        nullable=False,
    )

    absorption_delay_minutes = Column(
        Integer,
        nullable=False,
    )

    absorption_duration_minutes = Column(
        Integer,
        nullable=False,
    )

    curve_type = Column(
        String(50),
        nullable=False,
        default="linear",
    )

    curve_parameters = Column(JSON)

    classification_source = Column(
        String(100),
        nullable=False,
        default="carb_group_default_v1",
    )

    model_version = Column(
        String(100),
        nullable=False,
        default="deterministic_linear_v1",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    meal_carb_group = relationship("MealCarbGroup")
    patient = relationship("Patient")
    absorption_profile = relationship("CarbAbsorptionProfile")

    __table_args__ = (
        CheckConstraint(
            "absorption_delay_minutes >= 0",
            name="ck_meal_component_absorptions_delay",
        ),
        CheckConstraint(
            "absorption_duration_minutes > 0",
            name="ck_meal_component_absorptions_duration",
        ),
    )


class MealCalculation(Base):
    """Immutable snapshot of a meal dose calculation."""
    __tablename__ = "meal_calculations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    meal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    glucose_mg_dl = Column(Numeric(6, 2))
    target_glucose_mg_dl = Column(Numeric(6, 2))

    # Patient/time-of-day therapy snapshot.
    # This is the carb factor requested for the meal calculation.
    carb_factor_g_per_unit = Column(Numeric(8, 3))
    insulin_sensitivity_mg_dl_per_unit = Column(Numeric(8, 2))

    carbohydrate_total_grams = Column(Numeric(7, 1), nullable=False)

    carbohydrate_dose_units = Column(Numeric(8, 2))
    correction_dose_units = Column(Numeric(8, 2))
    calculated_dose_units = Column(Numeric(8, 2))

    # Step 3 immutable therapy/carb/strategy snapshot. These fields are
    # intentionally additive so calculation version 2 remains readable.
    meal_therapy_profile_id = Column(UUID(as_uuid=True))
    meal_basal_drift_mg_dl_per_hour = Column(Numeric(8, 2))

    base_carbohydrate_grams = Column(Numeric(8, 1))
    fat_protein_addon_percent = Column(Numeric(5, 2))
    fat_protein_addon_grams = Column(Numeric(8, 1))
    effective_carbohydrate_grams = Column(Numeric(8, 1))

    # B2.3 Warsaw-inspired delayed nutrient snapshot.
    # Explicitly separate from the legacy calculation-v3
    # fat_protein_addon_* fields above.
    fat_protein_model_mode = Column(String(20))
    fat_protein_model_scaling_percent = Column(Numeric(5, 2))

    fat_protein_fat_grams = Column(Numeric(8, 1))
    fat_protein_protein_grams = Column(Numeric(8, 1))

    fat_protein_fat_kcal = Column(Numeric(10, 2))
    fat_protein_protein_kcal = Column(Numeric(10, 2))
    fat_protein_total_kcal = Column(Numeric(10, 2))

    fat_protein_units = Column(Numeric(10, 4))

    fat_protein_theoretical_carb_equivalent_grams = Column(
        Numeric(10, 2)
    )
    fat_protein_scaled_carb_equivalent_grams = Column(
        Numeric(10, 2)
    )
    fat_protein_effective_carb_equivalent_grams = Column(
        Numeric(10, 2)
    )

    fat_protein_model_version = Column(String(50))

    absorption_profile_id = Column(UUID(as_uuid=True))
    absorption_profile_key = Column(String(50))
    absorption_duration_minutes = Column(Integer)
    absorption_delay_minutes = Column(Integer)
    absorption_classification_source = Column(String(50))

    dose_1_share_percent = Column(Numeric(5, 2))
    dose_2_share_percent = Column(Numeric(5, 2))
    dose_2_delay_minutes = Column(Integer)
    dose_2_timestamp = Column(DateTime)
    insulin_rounding_increment_units = Column(Numeric(6, 3))
    strategy_source = Column(String(50))
    strategy_version = Column(String(100))

    dose_2_therapy_profile_id = Column(UUID(as_uuid=True))
    dose_2_carb_factor_g_per_unit = Column(Numeric(8, 3))
    dose_2_insulin_sensitivity_mg_dl_per_unit = Column(Numeric(8, 2))
    dose_2_target_glucose_mg_dl = Column(Numeric(6, 2))
    dose_2_basal_drift_mg_dl_per_hour = Column(Numeric(8, 2))

    dose_1_carbohydrate_grams = Column(Numeric(8, 1))
    dose_2_carbohydrate_grams = Column(Numeric(8, 1))
    dose_1_carbohydrate_units = Column(Numeric(8, 3))
    dose_1_units = Column(Numeric(8, 3))
    dose_2_carbohydrate_units = Column(Numeric(8, 3))
    dose_2_units = Column(Numeric(8, 3))
    total_planned_dose_units = Column(Numeric(8, 3))
    manual_insulin_given_units = Column(Numeric(8, 3))

    calculation_version = Column(
        String(50),
        nullable=False,
        default="1"
    )
    notes = Column(Text)

    patient = relationship(
        "Patient",
        back_populates="meal_calculations"
    )
    meal = relationship(
        "Meal",
        back_populates="calculations"
    )
    dose_events = relationship(
        "MealDoseEvent",
        back_populates="calculation",
        cascade="all, delete-orphan",
        order_by="MealDoseEvent.dose_number",
    )


class MealDoseEvent(Base):
    """Planned versus actual execution of one split-dose component."""
    __tablename__ = "meal_dose_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meal_calculations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 1 = meal-time dose, 2 = delayed dose.
    dose_number = Column(Integer, nullable=False)

    planned_timestamp = Column(DateTime, nullable=False)
    planned_units = Column(Numeric(8, 3), nullable=False)

    actual_timestamp = Column(DateTime)
    actual_units = Column(Numeric(8, 3))

    # planned | given | adjusted | skipped | cancelled
    status = Column(String(30), nullable=False, default="planned")
    adjustment_reason = Column(String(100))
    notes = Column(Text)

    # Canonical insulin history entry created/linked when insulin is actually
    # administered. Keeping this nullable preserves skipped/cancelled events.
    insulin_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("insulin_events.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    patient = relationship("Patient", back_populates="meal_dose_events")
    meal = relationship("Meal", back_populates="dose_events")
    calculation = relationship("MealCalculation", back_populates="dose_events")
    insulin_event = relationship("InsulinEvent", back_populates="meal_dose_events")

    __table_args__ = (
        UniqueConstraint(
            "calculation_id",
            "dose_number",
            name="uq_meal_dose_event",
        ),
    )

class AdaptiveMealCalculation(Base):
    """
    Immutable B2.4a adaptive meal-accounting snapshot.

    This records how much insulin the meal currently requires based on actual
    consumption and actual meal insulin already administered.

    It is not yet a safe immediate insulin recommendation. Accumulated
    COB/FP/IOB, current physiological context and safety constraints belong to
    B2.4b-B2.4d.
    """

    __tablename__ = "adaptive_meal_calculations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    meal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    calculation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meal_calculations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    calculated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # Persisted-state input snapshots.
    #
    # NULL consumed carbohydrate means complete actual meal consumption is
    # still unknown. Planned carbohydrate is never substituted here.
    consumed_carbs_grams = Column(
        Numeric(10, 3),
        nullable=True,
    )

    # Warsaw-specific snapshot. NULL means this field does not apply
    # to the adaptive model that produced this row.
    fat_protein_effective_carb_equivalent_grams = Column(
        Numeric(10, 3),
        nullable=True,
    )

    insulin_to_carb_ratio = Column(
        Numeric(10, 3),
        nullable=False,
    )

    # Actual administered meal insulin only. Planned insulin is never counted.
    actual_administered_units = Column(
        Numeric(10, 3),
        nullable=False,
    )

    # Derived B2.4a meal-accounting outputs.
    carb_insulin_requirement_units = Column(
        Numeric(10, 3),
        nullable=True,
    )

    # Warsaw-specific derived output. NULL for non-Warsaw models.
    fat_protein_insulin_requirement_units = Column(
        Numeric(10, 3),
        nullable=True,
    )

    total_meal_requirement_units = Column(
        Numeric(10, 3),
        nullable=True,
    )

    remaining_meal_requirement_units = Column(
        Numeric(10, 3),
        nullable=True,
    )

    adaptive_calculation_version = Column(
        String(50),
        nullable=False,
    )

    # Identifies the independent model branch that produced this snapshot.
    adaptive_model_version = Column(
        String(50),
        nullable=False,
    )

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


class DoseStrategySettings(Base):
    """Patient-specific split-dose strategy and optimization bounds."""
    __tablename__ = "dose_strategy_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    dose_1_share_percent = Column(Numeric(5, 2), nullable=False, default=60)
    dose_2_delay_minutes = Column(Integer, nullable=False, default=75)
    insulin_rounding_increment_units = Column(
        Numeric(6, 3),
        nullable=False,
        default=Decimal("0.05"),
    )
    fat_protein_addon_percent = Column(Numeric(5, 2), nullable=False, default=0)

    # B2.3 patient-specific clinical configuration.
    # These fields are separate from the legacy fat_protein_addon_percent
    # calculation-v3 semantics above.
    fat_protein_mode = Column(
        String(20),
        nullable=False,
        default="disabled",
    )
    fat_protein_scaling_percent = Column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0"),
    )

    total_daily_dose_units = Column(Numeric(8, 2))
    basal_share_percent = Column(Numeric(5, 2))

    strategy_source = Column(String(50), nullable=False, default="manual")
    strategy_version = Column(String(100))

    min_dose_1_share_percent = Column(Numeric(5, 2))
    max_dose_1_share_percent = Column(Numeric(5, 2))
    min_dose_2_delay_minutes = Column(Integer)
    max_dose_2_delay_minutes = Column(Integer)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="dose_strategy_settings")


class CarbAbsorptionProfile(Base):
    """Patient-specific carbohydrate absorption profile definition."""
    __tablename__ = "carb_absorption_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_key = Column(String(50), nullable=False)
    profile_name = Column(String(100), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    absorption_delay_minutes = Column(Integer, nullable=False, default=10)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="carb_absorption_profiles")

    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "profile_key",
            name="uq_carb_absorption_patient_key",
        ),
    )


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
    time_period_start = Column(Time, nullable=False)
    time_period_end = Column(Time, nullable=False)
    insulin_sensitivity_mg_dl_per_unit = Column(Numeric(8, 2), nullable=False)
    insulin_to_carb_ratio = Column(Numeric(8, 2), nullable=False)
    basal_drift_mg_dl_per_hour = Column(Numeric(8, 2), nullable=False, default=0)
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

class PatientAbsorptionHistory(Base):
    """Derived historical 5-minute patient absorption estimate."""

    __tablename__ = "patient_absorption_history"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    interval_start = Column(DateTime, nullable=False)
    interval_end = Column(DateTime, nullable=False)

    base_absorbed_carbs_grams = Column(
        Numeric(12, 6),
        nullable=False,
    )

    hormonal_multiplier = Column(
        Numeric(10, 5),
        nullable=False,
        default=Decimal("1.0"),
    )

    activity_multiplier = Column(
        Numeric(10, 5),
        nullable=False,
        default=Decimal("1.0"),
    )

    adjusted_absorbed_carbs_grams = Column(
        Numeric(12, 6),
        nullable=False,
    )

    component_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    derivation_model = Column(
        String(100),
        nullable=False,
        default="deterministic_linear",
    )

    derivation_version = Column(
        String(100),
        nullable=False,
        default="deterministic_linear_v1",
    )

    derivation_mode = Column(
        String(50),
        nullable=False,
        default="original",
    )

    derived_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    patient = relationship("Patient")


class PatientAbsorptionForecast(Base):
    """Current rolling 5-minute patient absorption forecast."""

    __tablename__ = "patient_absorption_forecasts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    forecast_anchor_timestamp = Column(
        DateTime,
        nullable=False,
    )

    forecast_grid_start = Column(
        DateTime,
        nullable=False,
    )

    interval_start = Column(
        DateTime,
        nullable=False,
    )

    interval_end = Column(
        DateTime,
        nullable=False,
    )

    base_absorbed_carbs_grams = Column(
        Numeric(12, 6),
        nullable=False,
    )

    hormonal_multiplier = Column(
        Numeric(10, 5),
        nullable=False,
        default=Decimal("1.0"),
    )

    activity_multiplier = Column(
        Numeric(10, 5),
        nullable=False,
        default=Decimal("1.0"),
    )

    adjusted_absorbed_carbs_grams = Column(
        Numeric(12, 6),
        nullable=False,
    )

    component_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    deterministic_model_version = Column(
        String(100),
        nullable=False,
        default="deterministic_linear_v1",
    )

    ml_model_version = Column(String(100))

    ml_predicted_absorbed_carbs_grams = Column(
        Numeric(12, 6)
    )

    ml_lower_bound_grams = Column(
        Numeric(12, 6)
    )

    ml_upper_bound_grams = Column(
        Numeric(12, 6)
    )

    ml_confidence = Column(
        Numeric(8, 6)
    )

    forecast_generated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    patient = relationship("Patient")

class ClinicalModelSetting(Base):
    """
    Global administrative configuration for a calculation model.

    This is system/back-office configuration. It is deliberately separate
    from patient settings, patient-specific clinical configuration and model
    training metadata.
    """
    __tablename__ = "clinical_model_settings"

    __table_args__ = (
        UniqueConstraint(
            "model_key",
            "model_version",
            name="uq_clinical_model_settings_identity",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    model_key = Column(
        String(100),
        nullable=False,
    )

    model_version = Column(
        String(100),
        nullable=False,
    )

    role = Column(
        String(30),
        nullable=False,
    )

    enabled = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

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
