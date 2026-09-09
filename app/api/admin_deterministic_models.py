"""
Back-office patient deterministic-model administration.

This is clinical configuration for a specific patient and must not be
exposed through the patient application's settings UI.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Patient,
    PatientDeterministicModelSetting,
)
from app.schema.schemas import (
    PatientDeterministicModelSettingResponse,
    PatientDeterministicModelSettingUpdate,
)
from app.services.deterministic_model_config import (
    DeterministicModelConfigurationError,
    DeterministicModelIdentity,
    validate_deterministic_model_configuration,
)


router = APIRouter(
    prefix="/admin/patients",
    tags=["Admin Patient Deterministic Models"],
)


def _identity(
    model_key: str,
    model_version: str,
) -> DeterministicModelIdentity:
    return DeterministicModelIdentity(
        model_key=model_key,
        model_version=model_version,
    )


def _optional_iob_identity(
    *,
    model_key: str | None,
    model_version: str | None,
) -> DeterministicModelIdentity | None:
    if (model_key is None) != (model_version is None):
        raise DeterministicModelConfigurationError(
            "IOB model key and version must both be set or both be null"
        )

    if model_key is None:
        return None

    return _identity(
        model_key,
        model_version,
    )


def _identity_list(
    items,
) -> list[DeterministicModelIdentity]:
    return [
        _identity(
            item.model_key,
            item.model_version,
        )
        for item in (items or [])
    ]


async def _require_patient(
    *,
    db: AsyncSession,
    patient_id: UUID,
) -> None:
    result = await db.execute(
        select(Patient.id).where(
            Patient.id == patient_id
        )
    )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found",
        )


@router.get(
    "/{patient_id}/deterministic-model-settings",
    response_model=PatientDeterministicModelSettingResponse,
)
async def get_patient_deterministic_model_settings(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _require_patient(
        db=db,
        patient_id=patient_id,
    )

    result = await db.execute(
        select(PatientDeterministicModelSetting).where(
            PatientDeterministicModelSetting.patient_id
            == patient_id
        )
    )

    settings = result.scalar_one_or_none()

    if settings is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Patient deterministic model configuration "
                "not found"
            ),
        )

    return settings


@router.put(
    "/{patient_id}/deterministic-model-settings",
    response_model=PatientDeterministicModelSettingResponse,
)
async def put_patient_deterministic_model_settings(
    patient_id: UUID,
    update: PatientDeterministicModelSettingUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _require_patient(
        db=db,
        patient_id=patient_id,
    )

    try:
        cob_model = _identity(
            update.cob_model_key,
            update.cob_model_version,
        )

        iob_model = _optional_iob_identity(
            model_key=update.iob_model_key,
            model_version=update.iob_model_version,
        )

        allowed_cob_models = _identity_list(
            update.allowed_cob_models
        )

        allowed_iob_models = _identity_list(
            update.allowed_iob_models
        )

        validate_deterministic_model_configuration(
            cob_model=cob_model,
            iob_model=iob_model,
            insulin_accounting_policy=(
                update.insulin_accounting_policy
            ),
            active_insulin_time_minutes=(
                update.active_insulin_time_minutes
            ),
            patient_cob_model_selectable=(
                update.patient_cob_model_selectable
            ),
            patient_iob_model_selectable=(
                update.patient_iob_model_selectable
            ),
            allowed_cob_models=allowed_cob_models,
            allowed_iob_models=allowed_iob_models,
        )

    except DeterministicModelConfigurationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    result = await db.execute(
        select(PatientDeterministicModelSetting).where(
            PatientDeterministicModelSetting.patient_id
            == patient_id
        )
    )

    settings = result.scalar_one_or_none()

    if settings is None:
        settings = PatientDeterministicModelSetting(
            patient_id=patient_id,
        )
        db.add(settings)

    settings.cob_model_key = update.cob_model_key
    settings.cob_model_version = update.cob_model_version

    settings.iob_model_key = update.iob_model_key
    settings.iob_model_version = update.iob_model_version

    settings.insulin_accounting_policy = (
        update.insulin_accounting_policy
    )

    settings.active_insulin_time_minutes = (
        update.active_insulin_time_minutes
    )

    settings.patient_cob_model_selectable = (
        update.patient_cob_model_selectable
    )

    settings.patient_iob_model_selectable = (
        update.patient_iob_model_selectable
    )

    settings.allowed_cob_models = [
        item.model_dump()
        for item in (update.allowed_cob_models or [])
    ]

    settings.allowed_iob_models = [
        item.model_dump()
        for item in (update.allowed_iob_models or [])
    ]

    settings.cob_parameters = update.cob_parameters
    settings.iob_parameters = update.iob_parameters

    settings.config_source = "admin"
    settings.config_version = update.config_version
    settings.is_active = update.is_active

    await db.commit()
    await db.refresh(settings)

    return settings
