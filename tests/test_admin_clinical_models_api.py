"""
Tests for back-office clinical-model administration.

Clinical model exposure is global system-administration state.
It is deliberately separate from patient settings and model-training
metadata.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_clinical_models_returns_configured_models():
    from app.api import clinical_models

    primary = SimpleNamespace(
        model_key="primary",
        model_version="primary_v1",
        role="primary",
        enabled=True,
    )
    warsaw = SimpleNamespace(
        model_key="warsaw",
        model_version="warsaw_v1",
        role="alternative",
        enabled=False,
    )

    scalars = MagicMock()
    scalars.all.return_value = [primary, warsaw]

    result = MagicMock()
    result.scalars.return_value = scalars

    db = AsyncMock()
    db.execute.return_value = result

    models = await clinical_models.get_clinical_models(db=db)

    assert models == [primary, warsaw]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_alternative_model_enabled_state():
    from app.api import clinical_models
    from app.schema.schemas import ClinicalModelSettingUpdate

    warsaw = SimpleNamespace(
        model_key="warsaw",
        model_version="warsaw_v1",
        role="alternative",
        enabled=False,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = warsaw

    db = AsyncMock()
    db.execute.return_value = result

    updated = await clinical_models.update_clinical_model(
        model_key="warsaw",
        model_version="warsaw_v1",
        update=ClinicalModelSettingUpdate(enabled=True),
        db=db,
    )

    assert updated is warsaw
    assert warsaw.enabled is True
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(warsaw)


@pytest.mark.asyncio
async def test_update_clinical_model_returns_404_when_unknown():
    from fastapi import HTTPException

    from app.api import clinical_models
    from app.schema.schemas import ClinicalModelSettingUpdate

    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await clinical_models.update_clinical_model(
            model_key="unknown",
            model_version="unknown_v1",
            update=ClinicalModelSettingUpdate(enabled=True),
            db=db,
        )

    assert exc.value.status_code == 404
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_model_cannot_be_disabled():
    from fastapi import HTTPException

    from app.api import clinical_models
    from app.schema.schemas import ClinicalModelSettingUpdate

    primary = SimpleNamespace(
        model_key="primary",
        model_version="primary_v1",
        role="primary",
        enabled=True,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = primary

    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await clinical_models.update_clinical_model(
            model_key="primary",
            model_version="primary_v1",
            update=ClinicalModelSettingUpdate(enabled=False),
            db=db,
        )

    assert exc.value.status_code == 409
    assert primary.enabled is True
    db.commit.assert_not_awaited()


def test_clinical_model_admin_router_contract():
    from app.api import clinical_models

    routes = {
        (route.path, method)
        for route in clinical_models.router.routes
        for method in route.methods
    }

    assert (
        "/admin/clinical-models",
        "GET",
    ) in routes

    assert (
        "/admin/clinical-models/{model_key}/{model_version}",
        "PUT",
    ) in routes
