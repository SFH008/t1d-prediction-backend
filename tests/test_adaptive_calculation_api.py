"""
API/persistence integration contract for B2.4a adaptive meal accounting.

B2.4a recalculates one meal from authoritative persisted state. It is not yet
a safe immediate insulin recommendation.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.calculations import calculate_adaptive_meal
from app.models import AdaptiveMealCalculation, MealCalculation

from sqlalchemy.exc import SQLAlchemyError

def test_adaptive_response_schema_exists():
    from app.schema.schemas import AdaptiveMealCalculationResponse

    fields = AdaptiveMealCalculationResponse.model_fields

    assert "id" in fields
    assert "patient_id" in fields
    assert "meal_id" in fields
    assert "calculation_id" in fields
    assert "calculated_at" in fields

    assert "consumed_carbs_grams" in fields
    assert "fat_protein_effective_carb_equivalent_grams" in fields
    assert "insulin_to_carb_ratio" in fields
    assert "actual_administered_units" in fields

    assert "carb_insulin_requirement_units" in fields
    assert "fat_protein_insulin_requirement_units" in fields
    assert "total_meal_requirement_units" in fields
    assert "remaining_meal_requirement_units" in fields

    assert "adaptive_calculation_version" in fields


def test_adaptive_response_preserves_unknown_consumption():
    from app.schema.schemas import AdaptiveMealCalculationResponse

    nullable_fields = (
        "consumed_carbs_grams",
        "carb_insulin_requirement_units",
        "total_meal_requirement_units",
        "remaining_meal_requirement_units",
    )

    for field_name in nullable_fields:
        field = AdaptiveMealCalculationResponse.model_fields[field_name]
        assert field.is_required()


def test_adaptive_calculation_version_is_independent():
    from app.api.calculations import ADAPTIVE_MEAL_CALCULATION_VERSION

    assert (
        ADAPTIVE_MEAL_CALCULATION_VERSION
        == "adaptive_meal_requirement_v1"
    )


def test_build_adaptive_snapshot_uses_domain_result():
    from app.api.calculations import _build_adaptive_meal_calculation
    from app.services.adaptive_dose import AdaptiveMealRequirement

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    result = AdaptiveMealRequirement(
        consumed_carbs_grams=Decimal("30"),
        carb_insulin_requirement_units=Decimal("3"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20"),
        fat_protein_insulin_requirement_units=Decimal("2"),
        total_meal_requirement_units=Decimal("5"),
        actual_administered_units=Decimal("1.5"),
        remaining_meal_requirement_units=Decimal("3.5"),
    )

    snapshot = _build_adaptive_meal_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        insulin_to_carb_ratio=Decimal("10"),
        adaptive_model_version="primary_v1",
        result=result,
    )

    assert isinstance(snapshot, AdaptiveMealCalculation)

    assert snapshot.patient_id == patient_id
    assert snapshot.meal_id == meal_id
    assert snapshot.calculation_id == calculation_id

    assert snapshot.consumed_carbs_grams == Decimal("30")
    assert (
        snapshot.fat_protein_effective_carb_equivalent_grams
        == Decimal("20")
    )
    assert snapshot.insulin_to_carb_ratio == Decimal("10")
    assert snapshot.actual_administered_units == Decimal("1.5")

    assert snapshot.carb_insulin_requirement_units == Decimal("3")
    assert snapshot.fat_protein_insulin_requirement_units == Decimal("2")
    assert snapshot.total_meal_requirement_units == Decimal("5")
    assert snapshot.remaining_meal_requirement_units == Decimal("3.5")

    assert (
        snapshot.adaptive_calculation_version
        == "adaptive_meal_requirement_v1"
    )


def test_build_adaptive_snapshot_preserves_unknown_consumption():
    from app.api.calculations import _build_adaptive_meal_calculation
    from app.services.adaptive_dose import AdaptiveMealRequirement

    result = AdaptiveMealRequirement(
        consumed_carbs_grams=None,
        carb_insulin_requirement_units=None,
        fat_protein_effective_carb_equivalent_grams=Decimal("0"),
        fat_protein_insulin_requirement_units=Decimal("0"),
        total_meal_requirement_units=None,
        actual_administered_units=Decimal("0"),
        remaining_meal_requirement_units=None,
    )

    snapshot = _build_adaptive_meal_calculation(
        patient_id=uuid4(),
        meal_id=uuid4(),
        calculation_id=uuid4(),
        insulin_to_carb_ratio=Decimal("10"),
        adaptive_model_version="primary_v1",
        result=result,
    )

    assert snapshot.consumed_carbs_grams is None
    assert snapshot.carb_insulin_requirement_units is None
    assert snapshot.total_meal_requirement_units is None
    assert snapshot.remaining_meal_requirement_units is None


def test_adaptive_router_exposes_explicit_post_operation():
    from app.api.calculations import router

    matching = [
        route
        for route in router.routes
        if getattr(route, "path", "").endswith(
            "/calculations/{calculation_id}/adaptive"
        )
    ]

    assert len(matching) == 1
    assert "POST" in matching[0].methods


def test_adaptive_route_does_not_require_client_medical_payload():
    from app.api.calculations import router

    route = next(
        route
        for route in router.routes
        if getattr(route, "path", "").endswith(
            "/calculations/{calculation_id}/adaptive"
        )
    )

    assert list(route.dependant.body_params) == []

class _AdaptiveScalarResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _AdaptiveCalculationSession:
    """
    Minimal async-session fake for the B2.4a persistence boundary.

    Expected query order:
      1. originating MealCalculation
      2. current MealCarbGroup rows
      3. MealDoseEvent rows for the originating calculation
    """

    def __init__(self, *, calculation, components, dose_events):
        self.calculation = calculation
        self.components = components
        self.dose_events = dose_events

        self.execute_count = 0
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refresh_count = 0

    async def execute(self, stmt):
        self.execute_count += 1

        if self.execute_count == 1:
            return _AdaptiveScalarResult(
                scalar=self.calculation,
            )

        if self.execute_count == 2:
            return _AdaptiveScalarResult(
                rows=self.components,
            )

        if self.execute_count == 3:
            return _AdaptiveScalarResult(
                rows=self.dose_events,
            )

        raise AssertionError(
            f"Unexpected execute call #{self.execute_count}"
        )

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1

    async def refresh(self, item):
        self.refresh_count += 1

        # Simulate database-generated values needed by the response model.
        if item.id is None:
            item.id = uuid4()

        if item.calculated_at is None:
            item.calculated_at = datetime(2026, 9, 6, 8, 0)

class _ParallelAdaptiveCalculationSession(_AdaptiveCalculationSession):
    """
    Async-session fake for B2.4a.3 parallel model orchestration.

    Expected query order:
      1. originating MealCalculation
      2. current MealCarbGroup rows
      3. MealDoseEvent rows
      4. enabled ClinicalModelSetting rows
    """

    def __init__(
        self,
        *,
        calculation,
        components,
        dose_events,
        enabled_models,
    ):
        super().__init__(
            calculation=calculation,
            components=components,
            dose_events=dose_events,
        )
        self.enabled_models = enabled_models

    async def execute(self, stmt):
        if self.execute_count < 3:
            return await super().execute(stmt)

        self.execute_count += 1

        if self.execute_count == 4:
            return _AdaptiveScalarResult(
                rows=self.enabled_models,
            )

        raise AssertionError(
            f"Unexpected execute call #{self.execute_count}"
        )

class _FailingCommitParallelAdaptiveCalculationSession(
    _ParallelAdaptiveCalculationSession
):
    async def commit(self):
        self.commit_count += 1
        raise SQLAlchemyError("simulated parallel commit failure")

def _adaptive_originating_calculation(
    *,
    patient_id,
    meal_id,
    calculation_id,
):
    return MealCalculation(
        id=calculation_id,
        patient_id=patient_id,
        meal_id=meal_id,
        carbohydrate_total_grams=Decimal("60"),
        carb_factor_g_per_unit=Decimal("10"),

        # Immutable Primary-model snapshot.
        fat_protein_addon_percent=Decimal("20"),

        # Independent Warsaw snapshot. Primary must never consume this.
        fat_protein_effective_carb_equivalent_grams=Decimal("20"),
    )


@pytest.mark.asyncio
async def test_adaptive_route_loads_authoritative_state_and_persists_snapshot():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    components = [
        SimpleNamespace(
            consumed_carbs_grams=Decimal("20"),
            carbs_grams=Decimal("40"),
        ),
        SimpleNamespace(
            consumed_carbs_grams=Decimal("10"),
            carbs_grams=Decimal("20"),
        ),
    ]

    dose_events = [
        SimpleNamespace(
            status="given",
            actual_units=Decimal("1.5"),
            planned_units=Decimal("4"),
        ),
        SimpleNamespace(
            status="planned",
            actual_units=None,
            planned_units=Decimal("2"),
        ),
    ]

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=components,
        dose_events=dose_events,
    )

    result = await calculate_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    assert session.execute_count == 3
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.refresh_count == 1

    assert len(session.added) == 1
    assert result is session.added[0]

    # Actual consumption: 20 + 10 = 30 g.
    assert result.consumed_carbs_grams == Decimal("30")

    # Primary model reuses its immutable 20% add-on parameter against
    # actual consumption:
    #
    #   30 g actual + 20% = 36 g effective Primary carbohydrate
    #   36 / 10 = 3.6 U
    assert result.insulin_to_carb_ratio == Decimal("10")
    assert result.carb_insulin_requirement_units == Decimal("3.6")

    # Primary adaptive accounting must not consume the independently
    # snapshotted Warsaw fat/protein result.
    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None
    assert result.adaptive_model_version == "primary_v1"

    # Primary total requirement is therefore the carbohydrate requirement only.
    assert result.total_meal_requirement_units == Decimal("3.6")

    # Only actual given insulin counts. Planned 2 U is ignored.
    assert result.actual_administered_units == Decimal("1.5")
    assert result.remaining_meal_requirement_units == Decimal("2.1")


@pytest.mark.asyncio
async def test_adaptive_route_preserves_unknown_consumption():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    components = [
        SimpleNamespace(
            consumed_carbs_grams=Decimal("20"),
            carbs_grams=Decimal("40"),
        ),
        SimpleNamespace(
            consumed_carbs_grams=None,
            carbs_grams=Decimal("20"),
        ),
    ]

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=components,
        dose_events=[],
    )

    result = await calculate_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    # Planned carbs must never fill the unknown actual consumption.
    assert result.consumed_carbs_grams is None
    assert result.carb_insulin_requirement_units is None
    assert result.total_meal_requirement_units is None
    assert result.remaining_meal_requirement_units is None

    # Warsaw state is not consumed by the primary adaptive branch.
    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None
    assert result.adaptive_model_version == "primary_v1"

    assert result.actual_administered_units == Decimal("0")

    assert session.commit_count == 1
    assert session.refresh_count == 1


@pytest.mark.asyncio
async def test_adaptive_route_rejects_missing_originating_calculation():
    session = _AdaptiveCalculationSession(
        calculation=None,
        components=[],
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculate_adaptive_meal(
            patient_id=uuid4(),
            meal_id=uuid4(),
            calculation_id=uuid4(),
            db=session,
        )

    assert exc_info.value.status_code == 404

    # Stop immediately: no component/dose queries and no persistence.
    assert session.execute_count == 1
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_adaptive_route_rejects_calculation_from_different_patient():
    requested_patient_id = uuid4()
    actual_patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=actual_patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[],
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculate_adaptive_meal(
            patient_id=requested_patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 404
    assert session.execute_count == 1
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_adaptive_route_rejects_calculation_from_different_meal():
    patient_id = uuid4()
    requested_meal_id = uuid4()
    actual_meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=actual_meal_id,
        calculation_id=calculation_id,
    )

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[],
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculate_adaptive_meal(
            patient_id=patient_id,
            meal_id=requested_meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 404
    assert session.execute_count == 1
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_repeated_adaptive_calls_create_new_immutable_snapshots():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    components = [
        SimpleNamespace(
            consumed_carbs_grams=Decimal("30"),
            carbs_grams=Decimal("60"),
        ),
    ]

    first_session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=components,
        dose_events=[],
    )

    second_session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=components,
        dose_events=[],
    )

    first = await calculate_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=first_session,
    )

    second = await calculate_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=second_session,
    )

    assert len(first_session.added) == 1
    assert len(second_session.added) == 1

    assert first is not second
    assert first.id != second.id

    assert first.calculation_id == calculation_id
    assert second.calculation_id == calculation_id

@pytest.mark.asyncio
async def test_adaptive_route_rejects_missing_historical_icr_snapshot():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )
    calculation.carb_factor_g_per_unit = None

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[],
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculate_adaptive_meal(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 409
    assert (
        exc_info.value.detail
        == "Originating calculation lacks adaptive dosing snapshots"
    )

    # Validation occurs before current-state queries or persistence.
    assert session.execute_count == 1
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_primary_adaptive_route_ignores_historical_warsaw_snapshot():
    """
    The primary adaptive branch must not depend on or consume the
    originating Warsaw v1 fat/protein snapshot.
    """
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    # Deliberately provide a non-zero Warsaw result. The primary branch
    # must produce the same carbohydrate-only accounting regardless.
    calculation.fat_protein_effective_carb_equivalent_grams = Decimal("20")

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[],
    )

    result = await calculate_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3.6")

    # Warsaw must not cross-feed the primary adaptive calculation.
    assert result.fat_protein_effective_carb_equivalent_grams is None
    assert result.fat_protein_insulin_requirement_units is None
    assert result.adaptive_model_version == "primary_v1"

    assert result.total_meal_requirement_units == Decimal("3.6")
    assert result.remaining_meal_requirement_units == Decimal("3.6")

    assert session.execute_count == 3
    assert session.commit_count == 1


class _FailingCommitAdaptiveCalculationSession(
    _AdaptiveCalculationSession
):
    async def commit(self):
        self.commit_count += 1
        raise SQLAlchemyError("simulated commit failure")


@pytest.mark.asyncio
async def test_adaptive_route_rolls_back_when_persistence_fails():
    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    components = [
        SimpleNamespace(
            consumed_carbs_grams=Decimal("30"),
            carbs_grams=Decimal("60"),
        ),
    ]

    session = _FailingCommitAdaptiveCalculationSession(
        calculation=calculation,
        components=components,
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculate_adaptive_meal(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 500
    assert (
        exc_info.value.detail
        == "Failed to persist adaptive meal calculation"
    )

    assert session.commit_count == 1
    assert session.rollback_count == 1
    assert session.refresh_count == 0

def test_adaptive_response_exposes_model_provenance():
    from app.schema.schemas import AdaptiveMealCalculationResponse

    fields = AdaptiveMealCalculationResponse.model_fields

    assert "adaptive_model_version" in fields

def test_adaptive_snapshot_builder_requires_explicit_model_version():
    """
    Persistence must never silently assign a clinical model identity.

    Every adaptive branch must explicitly identify the model that produced
    the persisted result.
    """
    import inspect

    from app.api.calculations import _build_adaptive_meal_calculation

    signature = inspect.signature(_build_adaptive_meal_calculation)

    assert "adaptive_model_version" in signature.parameters

    parameter = signature.parameters["adaptive_model_version"]
    assert parameter.default is inspect.Parameter.empty


def test_adaptive_snapshot_builder_persists_warsaw_model_provenance():
    """
    A Warsaw adaptive result must be persisted as Warsaw and must retain
    its own Warsaw-specific fat/protein outputs.
    """
    from decimal import Decimal
    from uuid import uuid4

    from app.api.calculations import _build_adaptive_meal_calculation
    from app.services.adaptive_dose import AdaptiveMealRequirement

    result = AdaptiveMealRequirement(
        consumed_carbs_grams=Decimal("30"),
        fat_protein_effective_carb_equivalent_grams=Decimal("20"),
        carb_insulin_requirement_units=Decimal("3"),
        fat_protein_insulin_requirement_units=Decimal("2"),
        total_meal_requirement_units=Decimal("5"),
        actual_administered_units=Decimal("1"),
        remaining_meal_requirement_units=Decimal("4"),
    )

    snapshot = _build_adaptive_meal_calculation(
        patient_id=uuid4(),
        meal_id=uuid4(),
        calculation_id=uuid4(),
        insulin_to_carb_ratio=Decimal("10"),
        result=result,
        adaptive_model_version="warsaw_v1",
    )

    assert snapshot.adaptive_model_version == "warsaw_v1"
    assert (
        snapshot.fat_protein_effective_carb_equivalent_grams
        == Decimal("20")
    )
    assert (
        snapshot.fat_protein_insulin_requirement_units
        == Decimal("2")
    )
    assert snapshot.total_meal_requirement_units == Decimal("5")
    assert snapshot.remaining_meal_requirement_units == Decimal("4")

@pytest.mark.asyncio
async def test_warsaw_adaptive_route_uses_independent_warsaw_snapshot():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    # The originating calculation already carries the immutable Warsaw
    # effective FP equivalent. Make it explicit for this test.
    calculation.fat_protein_effective_carb_equivalent_grams = Decimal("20")

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[
            SimpleNamespace(
                status="given",
                planned_units=Decimal("2"),
                actual_units=Decimal("1.5"),
            ),
        ],
    )

    result = await calculations_api.calculate_warsaw_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    # Warsaw:
    #   actual carbohydrate = 30 g
    #   Warsaw effective FP equivalent = 20 g
    #   ICR = 10 g/U
    #
    #   carbohydrate requirement = 3 U
    #   Warsaw FP requirement    = 2 U
    #   total requirement        = 5 U
    #   actual insulin           = 1.5 U
    #   remaining                = 3.5 U

    assert result.consumed_carbs_grams == Decimal("30")
    assert result.carb_insulin_requirement_units == Decimal("3")

    assert (
        result.fat_protein_effective_carb_equivalent_grams
        == Decimal("20")
    )
    assert (
        result.fat_protein_insulin_requirement_units
        == Decimal("2")
    )

    assert result.total_meal_requirement_units == Decimal("5")
    assert result.actual_administered_units == Decimal("1.5")
    assert result.remaining_meal_requirement_units == Decimal("3.5")

    assert result.adaptive_model_version == "warsaw_v1"

    assert session.execute_count == 3
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.refresh_count == 1

    assert len(session.added) == 1
    assert result is session.added[0]

@pytest.mark.asyncio
async def test_warsaw_adaptive_route_rejects_missing_warsaw_snapshot():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    calculation.fat_protein_effective_carb_equivalent_grams = None

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[],
        dose_events=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculations_api.calculate_warsaw_adaptive_meal(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 409
    assert (
        exc_info.value.detail
        == "Originating calculation lacks Warsaw adaptive snapshots"
    )

    # Stop before loading current meal state or persisting anything.
    assert session.execute_count == 1
    assert session.added == []
    assert session.commit_count == 0

@pytest.mark.asyncio
async def test_warsaw_adaptive_route_is_independent_of_primary_addon_percent():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    calculation.fat_protein_effective_carb_equivalent_grams = Decimal("20")

    # Deliberately extreme Primary-only value.
    # Warsaw must not consume it.
    calculation.fat_protein_addon_percent = Decimal("80")

    session = _AdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[],
    )

    result = await calculations_api.calculate_warsaw_adaptive_meal(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    # Warsaw uses 30 g actual carbohydrate + its own 20 g FP equivalent.
    # Primary's 80% add-on must have no effect.
    assert result.carb_insulin_requirement_units == Decimal("3")
    assert (
        result.fat_protein_insulin_requirement_units
        == Decimal("2")
    )
    assert result.total_meal_requirement_units == Decimal("5")
    assert result.remaining_meal_requirement_units == Decimal("5")
    assert result.adaptive_model_version == "warsaw_v1"

def test_parallel_adaptive_response_supports_primary_and_generic_alternatives():
    from app.schema.schemas import (
        AdaptiveMealCalculationResponse,
        AdaptiveMealModelsResponse,
    )

    fields = AdaptiveMealModelsResponse.model_fields

    assert set(fields) == {
        "primary",
        "alternatives",
    }

    assert (
        fields["primary"].annotation
        is AdaptiveMealCalculationResponse
    )

    alternatives_annotation = fields["alternatives"].annotation

    assert getattr(alternatives_annotation, "__origin__", None) is list
    assert (
        alternatives_annotation.__args__[0]
        is AdaptiveMealCalculationResponse
    )

@pytest.mark.asyncio
async def test_parallel_adaptive_route_returns_primary_only_when_warsaw_disabled():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    # Warsaw is disabled, so its historical snapshot must not be required.
    calculation.fat_protein_effective_carb_equivalent_grams = None

    session = _ParallelAdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[
            SimpleNamespace(
                status="given",
                planned_units=Decimal("2"),
                actual_units=Decimal("1"),
            ),
        ],
        enabled_models=[
            SimpleNamespace(
                model_key="primary",
                model_version="primary_v1",
                role="primary",
                enabled=True,
            ),
        ],
    )

    response = await calculations_api.calculate_adaptive_models(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    assert response.primary.adaptive_model_version == "primary_v1"
    assert response.primary.consumed_carbs_grams == 30.0
    assert response.primary.total_meal_requirement_units == 3.6
    assert response.primary.remaining_meal_requirement_units == 2.6

    assert response.primary.fat_protein_effective_carb_equivalent_grams is None
    assert response.primary.fat_protein_insulin_requirement_units is None

    assert response.alternatives == []

    assert session.execute_count == 4
    assert len(session.added) == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.refresh_count == 1


@pytest.mark.asyncio
async def test_parallel_adaptive_route_returns_independent_primary_and_warsaw_results():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    # Primary uses its own immutable 20% add-on snapshot.
    calculation.fat_protein_addon_percent = Decimal("20")

    # Warsaw independently uses its immutable effective FP snapshot.
    calculation.fat_protein_effective_carb_equivalent_grams = Decimal("20")

    session = _ParallelAdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[
            SimpleNamespace(
                status="given",
                planned_units=Decimal("2"),
                actual_units=Decimal("1"),
            ),
        ],
        enabled_models=[
            SimpleNamespace(
                model_key="primary",
                model_version="primary_v1",
                role="primary",
                enabled=True,
            ),
            SimpleNamespace(
                model_key="warsaw",
                model_version="warsaw_v1",
                role="alternative",
                enabled=True,
            ),
        ],
    )

    response = await calculations_api.calculate_adaptive_models(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
        db=session,
    )

    primary = response.primary

    assert primary.adaptive_model_version == "primary_v1"

    # Primary:
    # actual carbs 30 g
    # + Primary FP add-on 20% = 6 g
    # effective = 36 g
    # / ICR 10 = 3.6 U
    # - actual insulin 1 U = 2.6 U
    assert primary.consumed_carbs_grams == 30.0
    assert primary.total_meal_requirement_units == 3.6
    assert primary.remaining_meal_requirement_units == 2.6

    assert primary.fat_protein_effective_carb_equivalent_grams is None
    assert primary.fat_protein_insulin_requirement_units is None

    assert len(response.alternatives) == 1

    warsaw = response.alternatives[0]

    assert warsaw.adaptive_model_version == "warsaw_v1"

    # Warsaw:
    # actual carbs 30 g / ICR 10 = 3 U
    # Warsaw FP equivalent 20 g / ICR 10 = 2 U
    # total = 5 U
    # - actual insulin 1 U = 4 U
    assert warsaw.consumed_carbs_grams == 30.0
    assert warsaw.fat_protein_effective_carb_equivalent_grams == 20.0
    assert warsaw.fat_protein_insulin_requirement_units == 2.0
    assert warsaw.total_meal_requirement_units == 5.0
    assert warsaw.remaining_meal_requirement_units == 4.0

    # Calculation, actual meal state and model configuration are each
    # loaded once and shared by the independent model branches.
    assert session.execute_count == 4

    # Both immutable model results are persisted in one transaction.
    assert len(session.added) == 2
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.refresh_count == 2

@pytest.mark.asyncio
async def test_parallel_adaptive_route_rejects_missing_warsaw_snapshot_when_enabled():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    calculation.fat_protein_effective_carb_equivalent_grams = None

    session = _ParallelAdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[
            SimpleNamespace(
                status="given",
                planned_units=Decimal("2"),
                actual_units=Decimal("1"),
            ),
        ],
        enabled_models=[
            SimpleNamespace(
                model_key="primary",
                model_version="primary_v1",
                role="primary",
                enabled=True,
            ),
            SimpleNamespace(
                model_key="warsaw",
                model_version="warsaw_v1",
                role="alternative",
                enabled=True,
            ),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculations_api.calculate_adaptive_models(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 409
    assert (
        exc_info.value.detail
        == "Originating calculation lacks Warsaw adaptive snapshots"
    )

    # Authoritative state and admin configuration were loaded,
    # but nothing was persisted.
    assert session.execute_count == 4
    assert session.added == []
    assert session.commit_count == 0
    assert session.rollback_count == 0
    assert session.refresh_count == 0


@pytest.mark.asyncio
async def test_parallel_adaptive_route_rolls_back_all_models_when_commit_fails():
    from app.api import calculations as calculations_api

    patient_id = uuid4()
    meal_id = uuid4()
    calculation_id = uuid4()

    calculation = _adaptive_originating_calculation(
        patient_id=patient_id,
        meal_id=meal_id,
        calculation_id=calculation_id,
    )

    calculation.fat_protein_addon_percent = Decimal("20")
    calculation.fat_protein_effective_carb_equivalent_grams = Decimal("20")

    session = _FailingCommitParallelAdaptiveCalculationSession(
        calculation=calculation,
        components=[
            SimpleNamespace(
                consumed_carbs_grams=Decimal("30"),
                carbs_grams=Decimal("60"),
            ),
        ],
        dose_events=[
            SimpleNamespace(
                status="given",
                planned_units=Decimal("2"),
                actual_units=Decimal("1"),
            ),
        ],
        enabled_models=[
            SimpleNamespace(
                model_key="primary",
                model_version="primary_v1",
                role="primary",
                enabled=True,
            ),
            SimpleNamespace(
                model_key="warsaw",
                model_version="warsaw_v1",
                role="alternative",
                enabled=True,
            ),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await calculations_api.calculate_adaptive_models(
            patient_id=patient_id,
            meal_id=meal_id,
            calculation_id=calculation_id,
            db=session,
        )

    assert exc_info.value.status_code == 500
    assert (
        exc_info.value.detail
        == "Failed to persist adaptive model calculations"
    )

    # Both snapshots reached the same transaction boundary.
    assert len(session.added) == 2

    assert {
        snapshot.adaptive_model_version
        for snapshot in session.added
    } == {
        "primary_v1",
        "warsaw_v1",
    }

    # The failed transaction is rolled back as one unit.
    assert session.execute_count == 4
    assert session.commit_count == 1
    assert session.rollback_count == 1
    assert session.refresh_count == 0