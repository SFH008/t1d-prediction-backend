"""
Back-office clinical-model administration.

Clinical model configuration is global system-administration state.
It is deliberately separate from patient settings and model-training
metadata.

Authentication/authorization will be added with the backend admin
security layer. These endpoints must never be exposed through the
patient Expo application's UI.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ClinicalModelSetting
from app.schema.schemas import (
    ClinicalModelSettingResponse,
    ClinicalModelSettingUpdate,
)


router = APIRouter(
    prefix="/admin/clinical-models",
    tags=["Admin Clinical Models"],
)


@router.get(
    "",
    response_model=list[ClinicalModelSettingResponse],
)
async def get_clinical_models(
    db: AsyncSession = Depends(get_db),
):
    """
    Return the global clinical-model configuration.
    """

    result = await db.execute(
        select(ClinicalModelSetting).order_by(
            ClinicalModelSetting.role,
            ClinicalModelSetting.model_key,
            ClinicalModelSetting.model_version,
        )
    )

    return result.scalars().all()


@router.put(
    "/{model_key}/{model_version}",
    response_model=ClinicalModelSettingResponse,
)
async def update_clinical_model(
    model_key: str,
    model_version: str,
    update: ClinicalModelSettingUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Enable or disable an administratively configured clinical model.

    Model identity, version and role are immutable through this endpoint.
    The primary model cannot be disabled.
    """

    result = await db.execute(
        select(ClinicalModelSetting).where(
            ClinicalModelSetting.model_key == model_key,
            ClinicalModelSetting.model_version == model_version,
        )
    )

    model = result.scalar_one_or_none()

    if model is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical model configuration not found",
        )

    if model.role == "primary" and update.enabled is False:
        raise HTTPException(
            status_code=409,
            detail="The primary clinical model cannot be disabled",
        )

    model.enabled = update.enabled

    await db.commit()
    await db.refresh(model)

    return model
