"""
Carb intake endpoints.
POST /patients/{patient_id}/carbs - Log carb entry
GET /patients/{patient_id}/carbs - Query carb entries
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal
import logging

from app.database import get_db
from app.models import CarbIntake, Patient
from app.schema.schemas import CarbIntakeCreate, CarbIntakeResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Carbs"])


@router.post("/patients/{patient_id}/carbs", response_model=CarbIntakeResponse, status_code=201)
async def create_carb_entry(
    patient_id: UUID,
    carb_create: CarbIntakeCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Log a carb intake entry.

    Args:
        patient_id: Patient UUID
        carb_create: Carb entry data (grams, food description, meal type)
        db: Database session

    Returns:
        Created carb entry
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Validate carbs
    if not (0 <= float(carb_create.carbs_grams) <= 500):
        raise HTTPException(
            status_code=400,
            detail="Carbs must be between 0 and 500 grams"
        )

    # Create entry
    carb_entry = CarbIntake(
        patient_id=patient_id,
        carbs_grams=Decimal(str(carb_create.carbs_grams)),
        food_description=carb_create.food_description,
        food_category=carb_create.food_category,
        meal_type=carb_create.meal_type,
        timestamp=carb_create.timestamp,
        source=carb_create.source or "manual",
        is_estimated=carb_create.is_estimated or False,
        confidence_level=carb_create.confidence_level
    )

    db.add(carb_entry)
    await db.commit()
    await db.refresh(carb_entry)

    logger.info(f"✅ Created carb entry: {carb_entry.id} ({carb_create.carbs_grams}g)")
    return carb_entry


@router.get("/patients/{patient_id}/carbs", response_model=list[CarbIntakeResponse])
async def get_carb_entries(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 24h)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    meal_type: str = Query(None, description="Filter by meal type (breakfast, lunch, snack, dinner)"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Query carb entries for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 24 hours)
        end_date: End timestamp (default: now)
        meal_type: Filter by meal type (breakfast, lunch, dinner, snack)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of carb entries
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
    stmt = select(CarbIntake).where(
        CarbIntake.patient_id == patient_id,
        CarbIntake.timestamp >= start_date,
        CarbIntake.timestamp <= end_date
    )

    # Apply meal type filter if provided
    if meal_type:
        stmt = stmt.where(CarbIntake.meal_type == meal_type)

    # Sort by timestamp descending, then apply pagination
    stmt = stmt.order_by(CarbIntake.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return entries