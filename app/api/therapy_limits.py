"""
Therapy limits endpoints.
GET /patients/{patient_id}/therapy-limits - Get therapy limits
POST /patients/{patient_id}/therapy-limits - Create therapy limit
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import logging

from app.database import get_db
from app.models import TherapyLimit, Patient
from app.schema.schemas import TherapyLimitCreate, TherapyLimitResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Therapy Limits"])


@router.get("/patients/{patient_id}/therapy-limits", response_model=list[TherapyLimitResponse])
async def get_therapy_limits(
    patient_id: UUID,
    active_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Get therapy limits for a patient.

    Args:
        patient_id: Patient UUID
        active_only: Return only active limits
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of therapy limits
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Build query
    stmt = select(TherapyLimit).where(TherapyLimit.patient_id == patient_id)

    if active_only:
        stmt = stmt.where(TherapyLimit.is_active == True)

    stmt = stmt.order_by(TherapyLimit.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    limits = result.scalars().all()

    return limits


@router.post("/patients/{patient_id}/therapy-limits", response_model=TherapyLimitResponse, status_code=201)
async def create_therapy_limit(
    patient_id: UUID,
    limit_create: TherapyLimitCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new therapy limit for a patient.

    Args:
        patient_id: Patient UUID
        limit_create: Therapy limit data
        db: Database session

    Returns:
        Created therapy limit
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate bounds
    if limit_create.lower_bound >= limit_create.upper_bound:
        raise HTTPException(
            status_code=400,
            detail="lower_bound must be less than upper_bound"
        )

    # Create limit
    therapy_limit = TherapyLimit(
        patient_id=patient_id,
        limit_type=limit_create.limit_type,
        lower_bound=limit_create.lower_bound,
        upper_bound=limit_create.upper_bound,
        is_hard_limit=limit_create.is_hard_limit,
        time_of_day_start=limit_create.time_of_day_start,
        time_of_day_end=limit_create.time_of_day_end,
        day_of_week=limit_create.day_of_week,
        is_active=True
    )

    db.add(therapy_limit)
    await db.commit()
    await db.refresh(therapy_limit)

    logger.info(f"✅ Created therapy limit: {therapy_limit.id}")
    return therapy_limit