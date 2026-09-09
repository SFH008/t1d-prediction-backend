"""
Patient-specific deterministic model configuration policy.

This module describes implementations that actually exist in the backend.
It must not advertise future IOB implementations before their engines exist.
"""

from __future__ import annotations

from dataclasses import dataclass


COB_MODEL_LINEAR = (
    "deterministic_linear",
    "deterministic_linear_v1",
)

SUPPORTED_COB_MODELS = frozenset({
    COB_MODEL_LINEAR,
})

# B2.4b.5/B2.4b.6 will add entries only when the corresponding
# deterministic IOB engines actually exist.
SUPPORTED_IOB_MODELS: frozenset[tuple[str, str]] = frozenset()

INSULIN_ACCOUNTING_POLICIES = frozenset({
    "total",
    "correction_only",
    "separated",
})


@dataclass(frozen=True)
class DeterministicModelIdentity:
    model_key: str
    model_version: str

    @property
    def identity(self) -> tuple[str, str]:
        return (
            self.model_key,
            self.model_version,
        )


class DeterministicModelConfigurationError(ValueError):
    """Invalid patient deterministic-model configuration."""


def validate_deterministic_model_configuration(
    *,
    cob_model: DeterministicModelIdentity,
    iob_model: DeterministicModelIdentity | None,
    insulin_accounting_policy: str,
    active_insulin_time_minutes: int | None,
    patient_cob_model_selectable: bool,
    patient_iob_model_selectable: bool,
    allowed_cob_models: list[DeterministicModelIdentity],
    allowed_iob_models: list[DeterministicModelIdentity],
) -> None:
    if cob_model.identity not in SUPPORTED_COB_MODELS:
        raise DeterministicModelConfigurationError(
            "Selected COB model is not implemented"
        )

    unsupported_cob = [
        model
        for model in allowed_cob_models
        if model.identity not in SUPPORTED_COB_MODELS
    ]
    if unsupported_cob:
        raise DeterministicModelConfigurationError(
            "Allowed COB models contain an implementation "
            "that is not available"
        )

    if iob_model is not None:
        if iob_model.identity not in SUPPORTED_IOB_MODELS:
            raise DeterministicModelConfigurationError(
                "Selected IOB model is not implemented"
            )

    unsupported_iob = [
        model
        for model in allowed_iob_models
        if model.identity not in SUPPORTED_IOB_MODELS
    ]
    if unsupported_iob:
        raise DeterministicModelConfigurationError(
            "Allowed IOB models contain an implementation "
            "that is not available"
        )

    if (
        insulin_accounting_policy
        not in INSULIN_ACCOUNTING_POLICIES
    ):
        raise DeterministicModelConfigurationError(
            "Invalid insulin accounting policy"
        )

    if (
        active_insulin_time_minutes is not None
        and active_insulin_time_minutes <= 0
    ):
        raise DeterministicModelConfigurationError(
            "Active insulin time must be greater than zero"
        )

    if patient_cob_model_selectable:
        if not allowed_cob_models:
            raise DeterministicModelConfigurationError(
                "Patient-selectable COB requires an allowed model set"
            )

        if cob_model.identity not in {
            model.identity
            for model in allowed_cob_models
        }:
            raise DeterministicModelConfigurationError(
                "Selected COB model must be included in "
                "the patient allowed model set"
            )

    if patient_iob_model_selectable:
        if iob_model is None:
            raise DeterministicModelConfigurationError(
                "Patient-selectable IOB requires a selected IOB model"
            )

        if not allowed_iob_models:
            raise DeterministicModelConfigurationError(
                "Patient-selectable IOB requires an allowed model set"
            )

        if iob_model.identity not in {
            model.identity
            for model in allowed_iob_models
        }:
            raise DeterministicModelConfigurationError(
                "Selected IOB model must be included in "
                "the patient allowed model set"
            )
