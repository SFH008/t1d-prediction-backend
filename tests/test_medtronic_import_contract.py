"""
Structural integration contract for Medtronic insulin ingestion.

The pure clinical/source normalization behavior is tested separately in
test_medtronic_insulin.py. These tests ensure the API importer uses that
normalizer and no longer restores the legacy lossy marker mapping.
"""

from pathlib import Path


IMPORTER = Path("app/api/imports.py")


def _source() -> str:
    return IMPORTER.read_text()


def test_importer_uses_medtronic_insulin_normalizer():
    source = _source()

    assert (
        "normalize_medtronic_insulin_marker"
        in source
    )
    assert "MEDTRONIC_INSULIN_SOURCE" in source


def test_importer_no_longer_uses_legacy_insulin_marker_map():
    source = _source()

    assert "insulin_type_map" not in source
    assert '"REWIND": "rewind"' not in source
    assert '"FILL": "fill"' not in source
    assert '"SUSPEND": "suspend"' not in source


def test_importer_persists_normalized_source_identity():
    source = _source()

    assert (
        "source_event_id="
        in source
    )
    assert (
        "normalized.source_event_id"
        in source
    )
    assert (
        "InsulinEvent.source_event_id"
        in source
    )


def test_importer_persists_normalized_delivery_semantics():
    source = _source()

    for field in (
        "delivery_class",
        "administration_mode",
        "purpose",
        "source_event_type",
        "source_activation_type",
        "programmed_units",
        "delivery_completed",
        "basal_rate",
    ):
        assert (
            f"{field}=" in source
        ), field


def test_idempotency_migration_is_partial_unique_index():
    migration = Path(
        "Database/migrations/"
        "020_add_insulin_source_event_idempotency.sql"
    ).read_text()

    assert "CREATE UNIQUE INDEX" in migration
    assert (
        "uq_insulin_events_patient_source_event"
        in migration
    )
    assert "patient_id" in migration
    assert "source_event_id" in migration
    assert (
        "WHERE source_event_id IS NOT NULL"
        in migration
    )
