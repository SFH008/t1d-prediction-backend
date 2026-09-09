"""Pure normalization of Medtronic CGM observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json


MEDTRONIC_GLUCOSE_SOURCE = "medtronic_minimed"


@dataclass(frozen=True)
class NormalizedMedtronicGlucoseReading:
    glucose_value_mg_dl: Decimal
    timestamp: datetime
    reading_type: str
    source: str
    source_event_id: str
    device_name: str | None
    is_valid: bool
    is_hypo: bool
    is_severe_hypo: bool
    is_hyper: bool
    is_severe_hyper: bool


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()

    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))

    return format(normalized, "f")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def build_medtronic_glucose_source_event_id(
    *,
    source_device_id: str | None,
    timestamp: datetime,
    glucose_value_mg_dl: Decimal,
) -> str:
    payload = {
        "identity_version": "medtronic_glucose_identity_v1",
        "source": MEDTRONIC_GLUCOSE_SOURCE,
        "source_device_id": source_device_id,
        "kind": "SG",
        "timestamp": timestamp.isoformat(),
        "glucose_value_mg_dl": _canonical_decimal(
            glucose_value_mg_dl
        ),
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return f"medtronic-glucose:v1:{digest}"


def normalize_medtronic_glucose_reading(
    entry: dict,
    *,
    source_device_id: str | None = None,
    device_name: str | None = None,
) -> NormalizedMedtronicGlucoseReading | None:
    if not isinstance(entry, dict):
        return None

    if entry.get("kind") != "SG":
        return None

    glucose = _decimal(entry.get("sg"))
    timestamp = _parse_timestamp(
        entry.get("timestamp")
    )

    if glucose is None or timestamp is None:
        return None

    if glucose < Decimal("40") or glucose > Decimal("400"):
        return None

    return NormalizedMedtronicGlucoseReading(
        glucose_value_mg_dl=glucose,
        timestamp=timestamp,
        reading_type="cgm",
        source=MEDTRONIC_GLUCOSE_SOURCE,
        source_event_id=(
            build_medtronic_glucose_source_event_id(
                source_device_id=source_device_id,
                timestamp=timestamp,
                glucose_value_mg_dl=glucose,
            )
        ),
        device_name=device_name,
        is_valid=True,
        is_hypo=glucose < Decimal("70"),
        is_severe_hypo=glucose < Decimal("54"),
        is_hyper=glucose > Decimal("180"),
        is_severe_hyper=glucose > Decimal("250"),
    )
