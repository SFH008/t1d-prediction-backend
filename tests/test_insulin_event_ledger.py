"""
B2.4b.1 factual insulin-ledger contract tests.

These tests intentionally cover schema/provenance only.
No IOB calculation belongs in this phase.
"""

from sqlalchemy import inspect

from app.models import InsulinEvent
from app.schema.schemas import (
    InsulinEventCreate,
    InsulinEventResponse,
)


def test_insulin_event_retains_actual_delivered_dose_as_canonical_fact():
    columns = {
        column.name: column
        for column in inspect(InsulinEvent).columns
    }

    assert "dose_units" in columns
    assert columns["dose_units"].nullable is False
    assert "timestamp" in columns
    assert columns["timestamp"].nullable is False


def test_insulin_event_has_independent_delivery_semantics():
    columns = {
        column.name
        for column in inspect(InsulinEvent).columns
    }

    assert {
        "delivery_class",
        "administration_mode",
        "purpose",
    } <= columns


def test_insulin_event_preserves_source_native_provenance():
    columns = {
        column.name
        for column in inspect(InsulinEvent).columns
    }

    assert {
        "source_event_type",
        "source_activation_type",
        "source_event_id",
        "source_device_id",
    } <= columns


def test_insulin_event_preserves_programmed_vs_actual_delivery():
    columns = {
        column.name
        for column in inspect(InsulinEvent).columns
    }

    assert "programmed_units" in columns
    assert "delivery_completed" in columns
    assert "dose_units" in columns


def test_insulin_create_schema_accepts_normalized_provenance():
    event = InsulinEventCreate(
        insulin_type="bolus",
        dose_units=0.05,
        timestamp="2026-08-13T06:57:25",
        delivery_method="pump",
        delivery_class="bolus",
        administration_mode="automated",
        purpose="correction",
        source_event_type="INSULIN",
        source_activation_type="AUTOCORRECTION",
        source_event_id="example-event",
        source_device_id="example-device",
        programmed_units=0.05,
        delivery_completed=True,
    )

    assert event.dose_units == 0.05
    assert event.delivery_class == "bolus"
    assert event.administration_mode == "automated"
    assert event.purpose == "correction"
    assert event.source_activation_type == "AUTOCORRECTION"
    assert event.programmed_units == 0.05
    assert event.delivery_completed is True


def test_insulin_response_exposes_normalized_provenance():
    fields = InsulinEventResponse.model_fields

    assert "delivery_class" in fields
    assert "administration_mode" in fields
    assert "purpose" in fields
    assert "source_event_type" in fields
    assert "source_activation_type" in fields
    assert "source_event_id" in fields
    assert "source_device_id" in fields
    assert "programmed_units" in fields
    assert "delivery_completed" in fields
