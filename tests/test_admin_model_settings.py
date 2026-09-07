"""
Administrative clinical-model configuration contract.

These settings control which calculation models the backend is permitted
to expose. They are system-administration state, not patient settings and
not model-training metadata.
"""

from app import models


def test_clinical_model_setting_has_required_administration_fields():
    model = models.ClinicalModelSetting

    assert model.__tablename__ == "clinical_model_settings"

    columns = model.__table__.columns

    required = {
        "id",
        "model_key",
        "model_version",
        "role",
        "enabled",
        "created_at",
        "updated_at",
    }

    assert required.issubset(set(columns.keys()))


def test_clinical_model_identity_is_unique():
    model = models.ClinicalModelSetting

    unique_constraints = [
        constraint
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]

    constrained_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in unique_constraints
    }

    assert ("model_key", "model_version") in constrained_column_sets


def test_model_setting_is_global_not_patient_scoped():
    columns = models.ClinicalModelSetting.__table__.columns

    assert "patient_id" not in columns


def test_model_setting_is_separate_from_training_metadata():
    assert (
        models.ClinicalModelSetting.__tablename__
        != models.ModelTrainingLog.__tablename__
    )


def test_primary_and_warsaw_can_be_represented_generically():
    model = models.ClinicalModelSetting

    primary = model(
        model_key="primary",
        model_version="primary_v1",
        role="primary",
        enabled=True,
    )

    warsaw = model(
        model_key="warsaw",
        model_version="warsaw_v1",
        role="alternative",
        enabled=False,
    )

    assert primary.model_key == "primary"
    assert primary.model_version == "primary_v1"
    assert primary.role == "primary"
    assert primary.enabled is True

    assert warsaw.model_key == "warsaw"
    assert warsaw.model_version == "warsaw_v1"
    assert warsaw.role == "alternative"
    assert warsaw.enabled is False
