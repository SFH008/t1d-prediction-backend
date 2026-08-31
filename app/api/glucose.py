"""
Glucose readings endpoints.
GET /patients/{patient_id}/glucose - Query glucose readings
GET /patients/{patient_id}/glucose/stats - Get glucose statistics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal
import logging

from app.database import get_db
from app.models import GlucoseReading, Patient
from app.schema.schemas import GlucoseReadingResponse, GlucoseStats

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Glucose"])


@router.get("/patients/{patient_id}/glucose", response_model=list[GlucoseReadingResponse])
async def get_glucose_readings(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 24h)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    hypo_only: bool = Query(False, description="Return only hypo readings (<70)"),
    severe_hypo_only: bool = Query(False, description="Return only severe hypo readings (<54)"),
    hyper_only: bool = Query(False, description="Return only hyper readings (>180)"),
    limit: int = Query(1000, ge=1, le=10000),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Query glucose readings for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 24 hours)
        end_date: End timestamp (default: now)
        hypo_only: Filter to hypo readings (<70)
        severe_hypo_only: Filter to severe hypo readings (<54)
        hyper_only: Filter to hyper readings (>180)
        limit: Max records to return
        skip: Records to skip (pagination)
        db: Database session

    Returns:
        List of glucose readings
    """
    # Verify patient exists
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Set default date range (last 24 hours)
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=1)

    # Build query
    stmt = select(GlucoseReading).where(
        GlucoseReading.patient_id == patient_id,
        GlucoseReading.timestamp >= start_date,
        GlucoseReading.timestamp <= end_date
    )

    # Apply filters
    if hypo_only:
        stmt = stmt.where(GlucoseReading.is_hypo == True)
    elif severe_hypo_only:
        stmt = stmt.where(GlucoseReading.is_severe_hypo == True)
    elif hyper_only:
        stmt = stmt.where(GlucoseReading.is_hyper == True)

    # Sort by timestamp descending, then apply pagination
    stmt = stmt.order_by(GlucoseReading.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    readings = result.scalars().all()

    return readings


@router.get("/patients/{patient_id}/glucose/stats", response_model=GlucoseStats)
async def get_glucose_stats(
    patient_id: UUID,
    start_date: datetime = Query(None, description="Start timestamp (default: last 24h)"),
    end_date: datetime = Query(None, description="End timestamp (default: now)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get glucose statistics for a patient.

    Args:
        patient_id: Patient UUID
        start_date: Start timestamp (default: last 24 hours)
        end_date: End timestamp (default: now)
        db: Database session

    Returns:
        Glucose statistics
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

    # Base query
    stmt = select(GlucoseReading).where(
        GlucoseReading.patient_id == patient_id,
        GlucoseReading.timestamp >= start_date,
        GlucoseReading.timestamp <= end_date
    )

    result = await db.execute(stmt)
    readings = result.scalars().all()

    if not readings:
        return GlucoseStats(
            total_readings=0,
            avg_glucose=0,
            min_glucose=0,
            max_glucose=0,
            hypo_count=0,
            severe_hypo_count=0,
            hyper_count=0,
            severe_hyper_count=0,
            time_in_range_percent=0
        )

    # Calculate statistics
    glucose_values = [float(r.glucose_value_mg_dl) for r in readings]

    total = len(readings)
    hypo_count = sum(1 for r in readings if r.is_hypo)
    severe_hypo_count = sum(1 for r in readings if r.is_severe_hypo)
    hyper_count = sum(1 for r in readings if r.is_hyper)
    severe_hyper_count = sum(1 for r in readings if r.is_severe_hyper)

    # Time in range (70-180)
    tir_count = sum(1 for v in glucose_values if 70 <= v <= 180)
    tir_percent = (tir_count / total * 100) if total > 0 else 0

    return GlucoseStats(
        total_readings=total,
        avg_glucose=round(sum(glucose_values) / len(glucose_values), 2),
        min_glucose=min(glucose_values),
        max_glucose=max(glucose_values),
        hypo_count=hypo_count,
        severe_hypo_count=severe_hypo_count,
        hyper_count=hyper_count,
        severe_hyper_count=severe_hyper_count,
        time_in_range_percent=round(tir_percent, 2)
    )