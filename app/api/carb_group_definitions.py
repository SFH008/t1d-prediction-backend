"""
Canonical carbohydrate group definition endpoints.

Definitions are system-managed configuration. Mutation will be restricted
to authenticated system administrators once backend authorization is added.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CarbGroupDefinition
from app.schema.schemas import CarbGroupDefinitionResponse


router = APIRouter(
    prefix="/admin/carb-group-definitions",
    tags=["Admin Carb Groups"],
)


@router.get(
    "",
    response_model=list[CarbGroupDefinitionResponse],
)
async def get_carb_group_definitions(
    db: AsyncSession = Depends(get_db),
):
    """
    Return canonical carbohydrate group definitions.

    This endpoint is read-only for now. Mutation will require
    authenticated system-admin authorization.
    """

    result = await db.execute(
        select(CarbGroupDefinition)
        .order_by(CarbGroupDefinition.group_number)
    )

    return result.scalars().all()
