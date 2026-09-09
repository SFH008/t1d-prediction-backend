"""Deterministic patient-model configuration policy tests."""

import pytest

from app.services.deterministic_model_config import (
    COB_MODEL_LINEAR,
    DeterministicModelConfigurationError,
    DeterministicModelIdentity,
    SUPPORTED_IOB_MODELS,
    validate_deterministic_model_configuration,
)


def linear_cob():
    return DeterministicModelIdentity(
        model_key=COB_MODEL_LINEAR[0],
        model_version=COB_MODEL_LINEAR[1],
    )


def validate(**overrides):
    values = {
        "cob_model": linear_cob(),
        "iob_model": None,
        "insulin_accounting_policy": "total",
        "active_insulin_time_minutes": None,
        "patient_cob_model_selectable": False,
        "patient_iob_model_selectable": False,
        "allowed_cob_models": [],
        "allowed_iob_models": [],
    }

    values.update(overrides)

    validate_deterministic_model_configuration(
        **values
    )


def test_current_linear_cob_configuration_is_valid():
    validate()


def test_no_iob_model_is_advertised_before_engine_exists():
    assert SUPPORTED_IOB_MODELS == frozenset()


def test_future_iob_identity_is_rejected_until_implemented():
    with pytest.raises(
        DeterministicModelConfigurationError,
        match="IOB model is not implemented",
    ):
        validate(
            iob_model=DeterministicModelIdentity(
                model_key="curvilinear",
                model_version="curvilinear_v1",
            )
        )


@pytest.mark.parametrize(
    "policy",
    [
        "total",
        "correction_only",
        "separated",
    ],
)
def test_supported_insulin_accounting_policies(
    policy,
):
    validate(
        insulin_accounting_policy=policy,
    )


def test_unknown_insulin_accounting_policy_is_rejected():
    with pytest.raises(
        DeterministicModelConfigurationError,
        match="Invalid insulin accounting policy",
    ):
        validate(
            insulin_accounting_policy="meal_only",
        )


def test_patient_selectable_cob_requires_allowed_set():
    with pytest.raises(
        DeterministicModelConfigurationError,
        match="allowed model set",
    ):
        validate(
            patient_cob_model_selectable=True,
        )


def test_patient_selectable_cob_accepts_selected_model():
    validate(
        patient_cob_model_selectable=True,
        allowed_cob_models=[linear_cob()],
    )


def test_positive_ait_can_be_preconfigured_without_iob_model():
    validate(
        active_insulin_time_minutes=180,
    )


def test_non_positive_ait_is_rejected():
    with pytest.raises(
        DeterministicModelConfigurationError,
        match="greater than zero",
    ):
        validate(
            active_insulin_time_minutes=0,
        )
