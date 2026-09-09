"""
Pure normalization of Medtronic pump markers into factual insulin events.

This module contains no database access.

Important boundaries:
- Only ACTUAL delivered insulin becomes an insulin event.
- Planned/recommended-but-not-delivered insulin is excluded.
- Pump state markers are not insulin events.
- Medtronic source semantics are preserved separately from normalized fields.
- source_event_id is deterministic so repeated API snapshots resolve to the
  same physiological event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


MEDTRONIC_INSULIN_SOURCE = "medtronic_minimed"


@dataclass(frozen=True)
class NormalizedMedtronicInsulinEvent:
    """Database-independent representation of one delivered insulin fact."""

    insulin_type: str
    dose_units: Decimal
    timestamp: datetime

    delivery_method: str
    source: str

    delivery_class: str
    administration_mode: str
    purpose: str

    source_event_type: str
    source_activation_type: str | None
    source_event_id: str
    source_device_id: str | None

    programmed_units: Decimal | None
    delivery_completed: bool | None

    basal_rate: Decimal | None
    device_name: str | None
    is_manual_entry: bool


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None

    if isinstance(value, str) and not value.strip():
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None


def _canonical_decimal(value: Decimal | None) -> str | None:
    """
    Produce a stable decimal representation for source identity.

    0.05, 0.050 and Decimal("0.0500") therefore identify the same
    physiological source value.
    """
    if value is None:
        return None

    normalized = value.normalize()

    # Decimal.normalize() may produce exponent notation. Fixed-point keeps
    # source identity readable and stable.
    text = format(normalized, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def build_medtronic_source_event_id(
    *,
    source_device_id: str | None,
    source_event_type: str,
    timestamp: datetime,
    source_activation_type: str | None,
    delivered_units: Decimal,
    programmed_units: Decimal | None,
    basal_rate: Decimal | None,
    bolus_type: str | None,
    delivery_completed: bool | None,
) -> str:
    """
    Build deterministic identity from immutable source facts.

    The current CareLink marker payload does not expose a native event UUID.
    This fingerprint deliberately uses source/device/event facts instead of
    generating a random application identifier.
    """
    payload = {
        "identity_version": "medtronic_event_identity_v1",
        "source": MEDTRONIC_INSULIN_SOURCE,
        "source_device_id": source_device_id,
        "source_event_type": source_event_type,
        "timestamp": timestamp.isoformat(),
        "source_activation_type": source_activation_type,
        "delivered_units": _canonical_decimal(delivered_units),
        "programmed_units": _canonical_decimal(programmed_units),
        "basal_rate": _canonical_decimal(basal_rate),
        "bolus_type": bolus_type,
        "delivery_completed": delivery_completed,
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return f"medtronic:v1:{digest}"


def normalize_medtronic_insulin_marker(
    marker: dict[str, Any],
    *,
    source_device_id: str | None = None,
    device_name: str | None = None,
) -> NormalizedMedtronicInsulinEvent | None:
    """
    Normalize one CareLink marker if and only if it represents delivered insulin.

    Supported source structures:

    AUTO_BASAL_DELIVERY
        bolusAmount       -> actual delivered dose_units
        maxAutoBasalRate  -> existing basal_rate field

    INSULIN + AUTOCORRECTION
        deliveredFastAmount  -> actual delivered dose_units
        programmedFastAmount -> programmed_units

    INSULIN + RECOMMENDED
        deliveredFastAmount  -> actual delivered dose_units
        programmedFastAmount -> programmed_units

    Other marker types return None.
    """

    marker_type = marker.get("type")

    if marker_type not in {
        "AUTO_BASAL_DELIVERY",
        "INSULIN",
    }:
        return None

    timestamp = _parse_timestamp(
        marker.get("timestamp")
    )
    if timestamp is None:
        return None

    data_values = (
        marker.get("data", {})
        .get("dataValues", {})
    )

    if not isinstance(data_values, dict):
        return None

    activation_type = data_values.get(
        "activationType"
    )
    bolus_type = data_values.get("bolusType")

    programmed_units: Decimal | None = None
    delivery_completed: bool | None = None
    basal_rate: Decimal | None = None

    if marker_type == "AUTO_BASAL_DELIVERY":
        dose_units = _decimal_or_none(
            data_values.get("bolusAmount")
        )

        basal_rate = _decimal_or_none(
            data_values.get("maxAutoBasalRate")
        )

        if dose_units is None or dose_units <= 0:
            return None

        insulin_type = "basal"
        delivery_class = "basal"
        administration_mode = "automated"
        purpose = "basal"

    else:
        dose_units = _decimal_or_none(
            data_values.get("deliveredFastAmount")
        )

        programmed_units = _decimal_or_none(
            data_values.get("programmedFastAmount")
        )

        completed_value = data_values.get(
            "completed"
        )

        # CareLink INSULIN records in the validated 780G sample expose
        # completed explicitly. Do not convert incomplete/recommended-only
        # records into delivered insulin facts.
        if completed_value is not True:
            return None

        delivery_completed = True

        if dose_units is None or dose_units <= 0:
            return None

        insulin_type = "bolus"
        delivery_class = "bolus"

        if activation_type == "AUTOCORRECTION":
            administration_mode = "automated"
            purpose = "correction"

        elif activation_type == "RECOMMENDED":
            # Preserve Medtronic semantics. "RECOMMENDED" is not assumed
            # to mean either manual or meal until source evidence proves it.
            administration_mode = "recommended"
            purpose = "unknown"

        else:
            administration_mode = "unknown"
            purpose = "unknown"

    source_event_id = (
        build_medtronic_source_event_id(
            source_device_id=source_device_id,
            source_event_type=marker_type,
            timestamp=timestamp,
            source_activation_type=activation_type,
            delivered_units=dose_units,
            programmed_units=programmed_units,
            basal_rate=basal_rate,
            bolus_type=bolus_type,
            delivery_completed=delivery_completed,
        )
    )

    return NormalizedMedtronicInsulinEvent(
        insulin_type=insulin_type,
        dose_units=dose_units,
        timestamp=timestamp,
        delivery_method="pump",
        source=MEDTRONIC_INSULIN_SOURCE,
        delivery_class=delivery_class,
        administration_mode=administration_mode,
        purpose=purpose,
        source_event_type=marker_type,
        source_activation_type=activation_type,
        source_event_id=source_event_id,
        source_device_id=source_device_id,
        programmed_units=programmed_units,
        delivery_completed=delivery_completed,
        basal_rate=basal_rate,
        device_name=device_name,
        is_manual_entry=False,
    )
