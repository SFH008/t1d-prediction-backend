"""Administrative deterministic-model route contract."""

from app.main import app


def test_admin_patient_deterministic_model_routes_registered():
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(
            route,
            "methods",
            set(),
        )
    }

    path = (
        "/admin/patients/{patient_id}/"
        "deterministic-model-settings"
    )

    assert (path, "GET") in routes
    assert (path, "PUT") in routes
