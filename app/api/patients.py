"""
Patient endpoints.
POST /patients - Create patient
GET /patients/{patient_id} - Get patient details
PUT /patients/{patient_id} - Update patient
GET /patients - List all patients
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import logging

from app.database import get_db
from app.models import Patient
from app.schema.schemas import PatientCreate, PatientUpdate, PatientResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("", response_model=PatientResponse, status_code=201)
async def create_patient(
    patient_create: PatientCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new patient.

    Args:
        patient_create: Patient creation data
        db: Database session

    Returns:
        Created patient details
    """
    # Check if patient already exists
    stmt = select(Patient).where(
        Patient.external_patient_id == patient_create.external_patient_id
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Patient with external_patient_id '{patient_create.external_patient_id}' already exists"
        )

    # Create new patient
    patient = Patient(
        first_name=patient_create.first_name,
        last_name=patient_create.last_name,
        external_patient_id=patient_create.external_patient_id,
        diabetes_type=patient_create.diabetes_type,
        time_zone=patient_create.time_zone,
        is_active=True
    )

    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info(f"✅ Created patient: {patient.id}")
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get patient details by ID.

    Args:
        patient_id: Patient UUID
        db: Database session

    Returns:
        Patient details
    """
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found"
        )

    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: UUID,
    patient_update: PatientUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update patient details.

    Args:
        patient_id: Patient UUID
        patient_update: Updated patient data
        db: Database session

    Returns:
        Updated patient details
    """
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found"
        )

    # Update fields
    if patient_update.first_name is not None:
        patient.first_name = patient_update.first_name
    if patient_update.last_name is not None:
        patient.last_name = patient_update.last_name
    if patient_update.time_zone is not None:
        patient.time_zone = patient_update.time_zone
    if patient_update.is_active is not None:
        patient.is_active = patient_update.is_active

    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info(f"✅ Updated patient: {patient.id}")
    return patient


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """
    List all patients with pagination.

    Args:
        skip: Number of records to skip
        limit: Maximum records to return
        active_only: Return only active patients
        db: Database session

    Returns:
        List of patients
    """
    stmt = select(Patient)

    if active_only:
        stmt = stmt.where(Patient.is_active == True)

    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    patients = result.scalars().all()

    return patients