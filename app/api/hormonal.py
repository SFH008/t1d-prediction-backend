"""
Hormonal context endpoints.
POST /patients/{patient_id}/hormonal-context - Log context (stress, sleep, etc.)
GET /patients/{patient_id}/hormonal-context - Query contexts
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal
import logging

from app.database import get_db
from app.models import HormonalContext, Patient
from app.schema.schemas import HormonalContextCreate, HormonalContextResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Hormonal Context"])


@router.post("/patients/{patient_id}/hormonal-context", response_model=HormonalContextResponse, status_code=201)
async def create_hormonal_context(
    patient_id: UUID,
    context_create: HormonalContextCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Log a hormonal or contextual factor (stress, sleep, menstrual cycle, illness, etc.).

    Args:
        patient_id: Patient UUID
        context_create: Context data
            - context_type: 'stress' | 'sleep_quality' | 'menstrual_cycle' | 'illness' | 'medication_change'
            - context_value: Text value (e.g., "high", "poor", "day_2")
            - numerical_value: Optional numeric value (0-100 for stress/sleep)
            - is_user_provided: Whether user entered this (True) or system learned it (False)
            - intensity_level: 'mild' | 'moderate' | 'severe'
            - duration_minutes: How long (for illness, stress episodes)
        db: Database session

    Returns:
        Created hormonal context entry
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate context type
    valid_types = ['stress', 'sleep_quality', 'menstrual_cycle', 'illness', 'medication_change', 'other']
    if context_create.context_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid context_type. Must be one of: {', '.join(valid_types)}"
        )

    # Validate numerical value if provided
    if context_create.numerical_value is not None:
        if not (0 <= float(context_create.numerical_value) <= 100):
            raise HTTPException(
                status_code=400,
                detail="numerical_value must be between 0 and 100"
            )

    # Create entry
    context = HormonalContext(
        patient_id=patient_id,
        context_type=context_create.context_type,
        context_value=context_create.context_value,
        numerical_value=Decimal(str(context_create.numerical_value)) if context_create.numerical_value else None,
        timestamp=context_create.timestamp,
        is_user_provided=context_create.is_user_provided or True,
        confidence_score=Decimal(str(context_create.confidence_score)) if context_create.confidence_score else None,
        source_type=context_create.source_type or ("manual" if context_create.is_user_provided else "learned"),
        intensity_level=context_create.intensity_level,
        duration_minutes=context_create.duration_minutes
    )

    db.add(context)
    await db.commit()
    await db.refresh(context)

    source = "user" if context.is_user_provided else "learned"
    logger.info(f"✅ Created {source} context: {context.id} ({context_create.context_type})")
    return context


@router.get("/patients/{patient_id}/hormonal-context", response_model=list[HormonalContextResponse])
async def get_hormonal_contexts(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 7 days)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    context_type: str = Query(None, description="Filter by type (stress, sleep_quality, menstrual_cycle, illness)"),
    user_provided_only: bool = Query(False, description="Show only user-provided entries (exclude learned)"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Query hormonal contexts for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 7 days)
        end_date: End timestamp (default: now)
        context_type: Filter by type
        user_provided_only: Show only manual entries (skip AI-learned)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of hormonal context entries
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Set default date range (last 7 days for contexts)
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    # Build query
    stmt = select(HormonalContext).where(
        HormonalContext.patient_id == patient_id,
        HormonalContext.timestamp >= start_date,
        HormonalContext.timestamp <= end_date
    )

    # Apply filters
    if context_type:
        stmt = stmt.where(HormonalContext.context_type == context_type)

    if user_provided_only:
        stmt = stmt.where(HormonalContext.is_user_provided == True)

    # Sort by timestamp descending, then apply pagination
    stmt = stmt.order_by(HormonalContext.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return entries