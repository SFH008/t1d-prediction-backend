"""
Insulin events endpoints.
GET /patients/{patient_id}/insulin - Query insulin events
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import UUID
import logging

from app.database import get_db
from app.models import InsulinEvent, Patient
from app.schema.schemas import InsulinEventResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Insulin"])


@router.get("/patients/{patient_id}/insulin", response_model=list[InsulinEventResponse])
async def get_insulin_events(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 24h)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    insulin_type: str = Query(None, description="Filter by insulin type (basal, bolus, etc.)"),
    limit: int = Query(1000, ge=1, le=10000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Query insulin events for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 24 hours)
        end_date: End timestamp (default: now)
        insulin_type: Filter by type (basal, bolus, rewind, fill, suspend)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of insulin events
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
    stmt = select(InsulinEvent).where(
        InsulinEvent.patient_id == patient_id,
        InsulinEvent.timestamp >= start_date,
        InsulinEvent.timestamp <= end_date
    )

    # Apply type filter if provided
    if insulin_type:
        stmt = stmt.where(InsulinEvent.insulin_type == insulin_type)

    # Sort by timestamp descending, then apply pagination
    stmt = stmt.order_by(InsulinEvent.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()

    return events