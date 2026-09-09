"""Structural contract for Medtronic CGM persistence."""

from pathlib import Path


IMPORTER = Path("app/api/imports.py")


def _source() -> str:
    return IMPORTER.read_text()


def test_importer_uses_medtronic_glucose_normalizer():
    source = _source()

    assert (
        "normalize_medtronic_glucose_reading"
        in source
    )
    assert "MEDTRONIC_GLUCOSE_SOURCE" in source


def test_importer_persists_glucose_source_identity():
    source = _source()

    assert (
        "GlucoseReading.source_event_id"
        in source
    )
    assert (
        "normalized.source_event_id"
        in source
    )


def test_importer_checks_existing_glucose_identity():
    source = _source()

    start = source.index(
        "# Process factual CGM observations."
    )
    end = source.index(
        "# Process factual delivered-insulin events.",
        start,
    )
    block = source[start:end]

    assert "select(" in block
    assert "GlucoseReading.id" in block
    assert "GlucoseReading.patient_id" in block
    assert "GlucoseReading.source" in block
    assert "GlucoseReading.source_event_id" in block
    assert "MEDTRONIC_GLUCOSE_SOURCE" in block


def test_glucose_import_no_longer_uses_legacy_source():
    source = _source()

    start = source.index(
        "# Process factual CGM observations."
    )
    end = source.index(
        "# Process factual delivered-insulin events.",
        start,
    )
    block = source[start:end]

    assert "medtronic_export" not in block
