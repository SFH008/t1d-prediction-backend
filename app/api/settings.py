"""
User settings endpoints.
GET /patients/{patient_id}/settings - Get user preferences
PUT /patients/{patient_id}/settings - Update settings
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import logging

from app.database import get_db
from app.models import UserSettings, Patient
from app.schema.schemas import UserSettingsResponse, UserSettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])


@router.get("/patients/{patient_id}/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get user settings and preferences for a patient.

    Args:
        patient_id: Patient UUID
        db: Database session

    Returns:
        User settings (safety bias, model selection, notifications, etc.)
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Get or create settings (with defaults)
    stmt = select(UserSettings).where(UserSettings.patient_id == patient_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        # Create default settings
        settings = UserSettings(
            patient_id=patient_id,
            glucose_unit_preference="mg/dl",
            carb_unit_preference="grams",
            insulin_unit_preference="units",
            notification_enabled=True,
            notification_low_threshold_mg_dl=70,
            notification_high_threshold_mg_dl=180,
            forecast_horizon_minutes=360,
            safety_bias="balanced",
            selected_model="ensemble",
            language_preference="en",
            display_theme="light"
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info(f"✅ Created default settings for patient: {patient_id}")

    return settings


@router.put("/patients/{patient_id}/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    patient_id: UUID,
    settings_update: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update user settings and preferences.

    Args:
        patient_id: Patient UUID
        settings_update: Settings to update
            - safety_bias: 'conservative' | 'balanced' | 'aggressive'
            - selected_model: 'arima' | 'iob_cob' | 'lstm' | 'ensemble'
            - notification_enabled: Enable/disable alerts
            - notification_low_threshold_mg_dl: Hypo alert threshold (default: 70)
            - notification_high_threshold_mg_dl: Hyper alert threshold (default: 180)
            - forecast_horizon_minutes: Prediction window (e.g., 360 = 6 hours)
            - carb_absorption_profile: 'fast' | 'standard' | 'slow'
            - language_preference: 'en' | 'da' | etc.
            - display_theme: 'light' | 'dark'
        db: Database session

    Returns:
        Updated settings
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Get or create settings
    stmt = select(UserSettings).where(UserSettings.patient_id == patient_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserSettings(patient_id=patient_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    # Validate safety_bias
    if settings_update.safety_bias:
        valid_bias = ['conservative', 'balanced', 'aggressive']
        if settings_update.safety_bias not in valid_bias:
            raise HTTPException(
                status_code=400,
                detail=f"safety_bias must be one of: {', '.join(valid_bias)}"
            )

    # Validate selected_model
    if settings_update.selected_model:
        valid_models = ['arima', 'iob_cob', 'lstm', 'ensemble']
        if settings_update.selected_model not in valid_models:
            raise HTTPException(
                status_code=400,
                detail=f"selected_model must be one of: {', '.join(valid_models)}"
            )

    # Validate thresholds
    if settings_update.notification_low_threshold_mg_dl:
        if not (40 <= float(settings_update.notification_low_threshold_mg_dl) <= 150):
            raise HTTPException(status_code=400, detail="Low threshold must be 40-150 mg/dL")

    if settings_update.notification_high_threshold_mg_dl:
        if not (150 <= float(settings_update.notification_high_threshold_mg_dl) <= 400):
            raise HTTPException(status_code=400, detail="High threshold must be 150-400 mg/dL")

    # Update fields
    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)

    db.add(settings)
    await db.commit()
    await db.refresh(settings)

    logger.info(f"✅ Updated settings for patient: {patient_id}")
    return settings