from decimal import Decimal

from app.services.medtronic_insulin import (
    build_medtronic_source_event_id,
    normalize_medtronic_insulin_marker,
)


DEVICE_ID = "pump-test-device"
DEVICE_NAME = "MMT-1886"


def test_normalizes_auto_basal_delivery():
    marker = {
        "type": "AUTO_BASAL_DELIVERY",
        "timestamp": "2026-09-01T00:31:12",
        "data": {
            "dataValues": {
                "bolusAmount": "0.02500000037252903",
                "maxAutoBasalRate": "0.31549999117851257",
            }
        },
    }

    event = normalize_medtronic_insulin_marker(
        marker,
        source_device_id=DEVICE_ID,
        device_name=DEVICE_NAME,
    )

    assert event is not None
    assert event.insulin_type == "basal"
    assert event.delivery_class == "basal"
    assert event.administration_mode == "automated"
    assert event.purpose == "basal"

    assert event.dose_units == Decimal(
        "0.02500000037252903"
    )
    assert event.basal_rate == Decimal(
        "0.31549999117851257"
    )

    assert event.programmed_units is None
    assert event.delivery_completed is None

    assert event.source_event_type == (
        "AUTO_BASAL_DELIVERY"
    )
    assert event.source_activation_type is None
    assert event.source_device_id == DEVICE_ID
    assert event.device_name == DEVICE_NAME
    assert event.is_manual_entry is False


def test_normalizes_autocorrection_as_automated_correction():
    marker = {
        "type": "INSULIN",
        "timestamp": "2026-09-01T06:57:25",
        "data": {
            "dataValues": {
                "insulinType": "UNKNOWN",
                "programmedFastAmount": "0.05",
                "deliveredFastAmount": "0.05",
                "activationType": "AUTOCORRECTION",
                "completed": True,
                "bolusType": "FAST",
            }
        },
    }

    event = normalize_medtronic_insulin_marker(
        marker,
        source_device_id=DEVICE_ID,
        device_name=DEVICE_NAME,
    )

    assert event is not None
    assert event.insulin_type == "bolus"
    assert event.delivery_class == "bolus"
    assert event.administration_mode == "automated"
    assert event.purpose == "correction"

    assert event.dose_units == Decimal("0.05")
    assert event.programmed_units == Decimal(
        "0.05"
    )
    assert event.delivery_completed is True

    assert event.source_event_type == "INSULIN"
    assert event.source_activation_type == (
        "AUTOCORRECTION"
    )


def test_recommended_preserves_source_semantics_without_inventing_meal_purpose():
    marker = {
        "type": "INSULIN",
        "timestamp": "2026-09-01T07:10:24",
        "data": {
            "dataValues": {
                "programmedFastAmount": "2.3",
                "deliveredFastAmount": "2.3",
                "activationType": "RECOMMENDED",
                "completed": True,
                "bolusType": "FAST",
            }
        },
    }

    event = normalize_medtronic_insulin_marker(
        marker,
        source_device_id=DEVICE_ID,
    )

    assert event is not None
    assert event.delivery_class == "bolus"
    assert event.administration_mode == (
        "recommended"
    )
    assert event.purpose == "unknown"
    assert event.dose_units == Decimal("2.3")
    assert event.programmed_units == Decimal(
        "2.3"
    )
    assert event.source_activation_type == (
        "RECOMMENDED"
    )


def test_non_insulin_marker_is_not_converted_to_insulin_event():
    marker = {
        "type": "LOW_GLUCOSE_SUSPENDED",
        "timestamp": "2026-09-01T12:00:00",
        "data": {
            "dataValues": {}
        },
    }

    assert (
        normalize_medtronic_insulin_marker(
            marker,
            source_device_id=DEVICE_ID,
        )
        is None
    )


def test_meal_marker_is_not_converted_to_insulin_event():
    marker = {
        "type": "MEAL",
        "timestamp": "2026-09-01T07:10:24",
        "data": {
            "dataValues": {
                "amount": 82.0
            }
        },
    }

    assert (
        normalize_medtronic_insulin_marker(
            marker,
            source_device_id=DEVICE_ID,
        )
        is None
    )


def test_incomplete_insulin_record_is_not_delivered_insulin():
    marker = {
        "type": "INSULIN",
        "timestamp": "2026-09-01T07:10:24",
        "data": {
            "dataValues": {
                "programmedFastAmount": "2.3",
                "deliveredFastAmount": "0",
                "activationType": "RECOMMENDED",
                "completed": False,
                "bolusType": "FAST",
            }
        },
    }

    assert (
        normalize_medtronic_insulin_marker(
            marker,
            source_device_id=DEVICE_ID,
        )
        is None
    )


def test_zero_auto_basal_is_not_an_insulin_delivery_fact():
    marker = {
        "type": "AUTO_BASAL_DELIVERY",
        "timestamp": "2026-09-01T07:10:24",
        "data": {
            "dataValues": {
                "bolusAmount": "0",
                "maxAutoBasalRate": "0.3155",
            }
        },
    }

    assert (
        normalize_medtronic_insulin_marker(
            marker,
            source_device_id=DEVICE_ID,
        )
        is None
    )


def test_source_event_identity_is_stable_for_repeated_snapshot():
    marker = {
        "type": "INSULIN",
        "timestamp": "2026-09-01T06:57:25",
        "data": {
            "dataValues": {
                "programmedFastAmount": "0.0500",
                "deliveredFastAmount": "0.050",
                "activationType": "AUTOCORRECTION",
                "completed": True,
                "bolusType": "FAST",
            }
        },
    }

    first = normalize_medtronic_insulin_marker(
        marker,
        source_device_id=DEVICE_ID,
    )
    second = normalize_medtronic_insulin_marker(
        marker,
        source_device_id=DEVICE_ID,
    )

    assert first is not None
    assert second is not None
    assert first.source_event_id == (
        second.source_event_id
    )


def test_source_identity_normalizes_equivalent_decimal_formatting():
    from datetime import datetime

    first = build_medtronic_source_event_id(
        source_device_id=DEVICE_ID,
        source_event_type="INSULIN",
        timestamp=datetime.fromisoformat(
            "2026-09-01T06:57:25"
        ),
        source_activation_type="AUTOCORRECTION",
        delivered_units=Decimal("0.0500"),
        programmed_units=Decimal("0.050"),
        basal_rate=None,
        bolus_type="FAST",
        delivery_completed=True,
    )

    second = build_medtronic_source_event_id(
        source_device_id=DEVICE_ID,
        source_event_type="INSULIN",
        timestamp=datetime.fromisoformat(
            "2026-09-01T06:57:25"
        ),
        source_activation_type="AUTOCORRECTION",
        delivered_units=Decimal("0.05"),
        programmed_units=Decimal("0.05"),
        basal_rate=None,
        bolus_type="FAST",
        delivery_completed=True,
    )

    assert first == second


def test_distinct_physiological_events_receive_distinct_identity():
    first_marker = {
        "type": "AUTO_BASAL_DELIVERY",
        "timestamp": "2026-09-01T00:31:12",
        "data": {
            "dataValues": {
                "bolusAmount": "0.025",
                "maxAutoBasalRate": "0.3155",
            }
        },
    }

    second_marker = {
        **first_marker,
        "timestamp": "2026-09-01T00:36:15",
    }

    first = normalize_medtronic_insulin_marker(
        first_marker,
        source_device_id=DEVICE_ID,
    )
    second = normalize_medtronic_insulin_marker(
        second_marker,
        source_device_id=DEVICE_ID,
    )

    assert first is not None
    assert second is not None
    assert first.source_event_id != (
        second.source_event_id
    )
