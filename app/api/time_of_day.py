"""
Time-of-day profile endpoints.
GET /patients/{patient_id}/time-of-day-profiles - Get ISF/ICR profiles
POST /patients/{patient_id}/time-of-day-profiles - Create profile
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from decimal import Decimal
import logging

from app.database import get_db
from app.models import TimeOfDayProfile, Patient
from app.schema.schemas import TimeOfDayProfileCreate, TimeOfDayProfileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Time-of-Day Profiles"])


@router.post("/patients/{patient_id}/time-of-day-profiles", response_model=TimeOfDayProfileResponse, status_code=201)
async def create_time_of_day_profile(
    patient_id: UUID,
    profile_create: TimeOfDayProfileCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create an insulin sensitivity factor (ISF) and insulin-to-carb ratio (ICR) profile for a time period.

    Args:
        patient_id: Patient UUID
        profile_create: Profile data
            - profile_name: Descriptive name (e.g., "Morning", "Afternoon", "Evening")
            - time_period_start: HH:MM format (e.g., "06:00")
            - time_period_end: HH:MM format (e.g., "12:00")
            - insulin_sensitivity_mg_dl_per_unit: ISF (how much 1 unit insulin lowers BG)
            - insulin_to_carb_ratio: ICR (1 unit covers X grams carbs)
            - target_glucose_min/max: Target range for this time period
            - day_of_week: Optional (0=Sun...6=Sat, NULL=all days)
        db: Database session

    Returns:
        Created profile
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate time format
    try:
        start_h, start_m = map(int, profile_create.time_period_start.split(':'))
        end_h, end_m = map(int, profile_create.time_period_end.split(':'))

        if not (0 <= start_h <= 23 and 0 <= start_m <= 59):
            raise ValueError()
        if not (0 <= end_h <= 23 and 0 <= end_m <= 59):
            raise ValueError()
    except:
        raise HTTPException(status_code=400, detail="Time must be in HH:MM format")

    # Validate ratios
    if float(profile_create.insulin_sensitivity_mg_dl_per_unit) <= 0:
        raise HTTPException(status_code=400, detail="ISF must be positive")

    if float(profile_create.insulin_to_carb_ratio) <= 0:
        raise HTTPException(status_code=400, detail="ICR must be positive")

    # Validate day of week
    if profile_create.day_of_week is not None:
        if not (0 <= profile_create.day_of_week <= 6):
            raise HTTPException(status_code=400, detail="day_of_week must be 0-6 (0=Sunday)")

    # Create profile
    profile = TimeOfDayProfile(
        patient_id=patient_id,
        profile_name=profile_create.profile_name,
        time_period_start=profile_create.time_period_start,
        time_period_end=profile_create.time_period_end,
        insulin_sensitivity_mg_dl_per_unit=Decimal(str(profile_create.insulin_sensitivity_mg_dl_per_unit)),
        insulin_to_carb_ratio=Decimal(str(profile_create.insulin_to_carb_ratio)),
        target_glucose_min_mg_dl=Decimal(str(profile_create.target_glucose_min_mg_dl)) if profile_create.target_glucose_min_mg_dl else None,
        target_glucose_max_mg_dl=Decimal(str(profile_create.target_glucose_max_mg_dl)) if profile_create.target_glucose_max_mg_dl else None,
        day_of_week=profile_create.day_of_week,
        is_active=True
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    logger.info(f"✅ Created time-of-day profile: {profile.id} ({profile_create.profile_name})")
    return profile


@router.get("/patients/{patient_id}/time-of-day-profiles", response_model=list[TimeOfDayProfileResponse])
async def get_time_of_day_profiles(
    patient_id: UUID,
    active_only: bool = Query(True, description="Return only active profiles"),
    day_of_week: int = Query(None, description="Filter by day of week (0=Sunday, 6=Saturday)"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Get time-of-day profiles (ISF/ICR by time period) for a patient.

    Args:
        patient_id: Patient UUID
        active_only: Return only active profiles
        day_of_week: Filter by specific day (0-6, None=all days)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of time-of-day profiles
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Build query
    stmt = select(TimeOfDayProfile).where(TimeOfDayProfile.patient_id == patient_id)

    if active_only:
        stmt = stmt.where(TimeOfDayProfile.is_active == True)

    if day_of_week is not None:
        # Match either the specific day OR NULL (all days)
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(
                TimeOfDayProfile.day_of_week == day_of_week,
                TimeOfDayProfile.day_of_week == None
            )
        )

    # Sort by time period start, then apply pagination
    stmt = stmt.order_by(TimeOfDayProfile.time_period_start).offset(skip).limit(limit)

    result = await db.execute(stmt)
    profiles = result.scalars().all()

    return profiles