"""
Activity endpoints.
POST /patients/{patient_id}/activities - Log activity
GET /patients/{patient_id}/activities - Query activities
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal
import logging

from app.database import get_db
from app.models import Activity, Patient
from app.schema.schemas import ActivityCreate, ActivityResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Activities"])


@router.post("/patients/{patient_id}/activities", response_model=ActivityResponse, status_code=201)
async def create_activity(
    patient_id: UUID,
    activity_create: ActivityCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Log a physical activity entry.

    Args:
        patient_id: Patient UUID
        activity_create: Activity data (type, intensity, duration)
        db: Database session

    Returns:
        Created activity entry
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate duration
    if activity_create.duration_minutes < 1 or activity_create.duration_minutes > 1440:
        raise HTTPException(
            status_code=400,
            detail="Duration must be between 1 and 1440 minutes"
        )

    # Create entry
    activity = Activity(
        patient_id=patient_id,
        activity_type=activity_create.activity_type,
        intensity=activity_create.intensity,
        duration_minutes=activity_create.duration_minutes,
        calories_burned=activity_create.calories_burned,
        heart_rate_avg=activity_create.heart_rate_avg,
        heart_rate_max=activity_create.heart_rate_max,
        timestamp=activity_create.timestamp,
        source=activity_create.source or "manual"
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(f"✅ Created activity: {activity.id} ({activity_create.activity_type})")
    return activity


@router.get("/patients/{patient_id}/activities", response_model=list[ActivityResponse])
async def get_activities(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 24h)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    activity_type: str = Query(None, description="Filter by activity type (running, cycling, walking, etc.)"),
    intensity: str = Query(None, description="Filter by intensity (light, moderate, vigorous)"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Query activities for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 24 hours)
        end_date: End timestamp (default: now)
        activity_type: Filter by type (running, cycling, walking, swimming, etc.)
        intensity: Filter by intensity (light, moderate, vigorous)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of activity entries
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Set default date range
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=1)

    # Build query
    stmt = select(Activity).where(
        Activity.patient_id == patient_id,
        Activity.timestamp >= start_date,
        Activity.timestamp <= end_date
    )

    # Apply filters
    if activity_type:
        stmt = stmt.where(Activity.activity_type == activity_type)
    if intensity:
        stmt = stmt.where(Activity.intensity == intensity)

    # Sort by timestamp descending, then apply pagination
    stmt = stmt.order_by(Activity.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return entries