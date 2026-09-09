from app.services.medtronic_glucose import (
    normalize_medtronic_glucose_reading,
)


def _entry(
    *,
    sg=105,
    timestamp="2026-09-01T14:31:00",
):
    return {
        "kind": "SG",
        "sg": sg,
        "timestamp": timestamp,
    }


def test_normalizes_medtronic_sg():
    reading = normalize_medtronic_glucose_reading(
        _entry(),
        source_device_id="pump-1",
        device_name="MMT-1886",
    )

    assert reading is not None
    assert reading.glucose_value_mg_dl == 105
    assert reading.reading_type == "cgm"
    assert reading.source == "medtronic_minimed"
    assert reading.device_name == "MMT-1886"
    assert reading.is_valid is True


def test_classifies_thresholds():
    reading = normalize_medtronic_glucose_reading(
        _entry(sg=53)
    )

    assert reading is not None
    assert reading.is_hypo is True
    assert reading.is_severe_hypo is True
    assert reading.is_hyper is False
    assert reading.is_severe_hyper is False


def test_rejects_non_sg():
    assert (
        normalize_medtronic_glucose_reading(
            {"kind": "CALIBRATION", "sg": 100}
        )
        is None
    )


def test_rejects_out_of_range_glucose():
    assert (
        normalize_medtronic_glucose_reading(
            _entry(sg=39)
        )
        is None
    )

    assert (
        normalize_medtronic_glucose_reading(
            _entry(sg=401)
        )
        is None
    )


def test_repeated_snapshot_has_same_identity():
    first = normalize_medtronic_glucose_reading(
        _entry(),
        source_device_id="pump-1",
    )
    second = normalize_medtronic_glucose_reading(
        _entry(),
        source_device_id="pump-1",
    )

    assert first is not None
    assert second is not None
    assert (
        first.source_event_id
        == second.source_event_id
    )


def test_equivalent_glucose_format_has_same_identity():
    first = normalize_medtronic_glucose_reading(
        _entry(sg="105.0"),
        source_device_id="pump-1",
    )
    second = normalize_medtronic_glucose_reading(
        _entry(sg="105.00"),
        source_device_id="pump-1",
    )

    assert first is not None
    assert second is not None
    assert (
        first.source_event_id
        == second.source_event_id
    )


def test_different_timestamp_has_different_identity():
    first = normalize_medtronic_glucose_reading(
        _entry(
            timestamp="2026-09-01T14:26:00"
        ),
        source_device_id="pump-1",
    )
    second = normalize_medtronic_glucose_reading(
        _entry(
            timestamp="2026-09-01T14:31:00"
        ),
        source_device_id="pump-1",
    )

    assert first is not None
    assert second is not None
    assert (
        first.source_event_id
        != second.source_event_id
    )


def test_corrected_value_same_timestamp_is_distinct():
    first = normalize_medtronic_glucose_reading(
        _entry(sg=104),
        source_device_id="pump-1",
    )
    second = normalize_medtronic_glucose_reading(
        _entry(sg=105),
        source_device_id="pump-1",
    )

    assert first is not None
    assert second is not None
    assert (
        first.source_event_id
        != second.source_event_id
    )
