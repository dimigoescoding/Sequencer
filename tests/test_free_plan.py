"""Bounds and storage chosen for a Render Free web service."""

import pytest
from apps.datasets.storage import DatabaseStorage
from apps.optimisation.services.runner import SolveBusy, execute
from apps.optimisation.services.scaling import (
    MAX_DISTANCE_FOUNDATIONS,
    MAX_INCLUDED_FOUNDATIONS,
    MAX_SOLVER_TIME_LIMIT_SECONDS,
)
from apps.scenarios.forms import VesselSettingsForm
from apps.scenarios.models import VesselSettings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_health_check_is_public(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"


def test_database_storage_round_trip():
    storage = DatabaseStorage()
    name = storage.save("datasets/sample.xlsx", ContentFile(b"workbook-bytes"))
    assert storage.exists(name)
    assert storage.size(name) == len(b"workbook-bytes")
    with storage.open(name) as handle:
        assert handle.read() == b"workbook-bytes"
    storage.delete(name)
    assert storage.exists(name) is False


def test_solver_time_form_rejects_a_limit_the_free_request_cannot_finish():
    settings = VesselSettings(max_foundations_per_trip=4, solver_time_limit_seconds=20)
    form = VesselSettingsForm(
        data={
            "max_foundations_per_trip": 4,
            "allow_partial_final_trip": True,
            "solver_time_limit_seconds": 60,
        },
        instance=settings,
    )
    assert form.is_valid() is False
    assert "solver_time_limit_seconds" in form.errors
    assert MAX_SOLVER_TIME_LIMIT_SECONDS == 30
    assert MAX_INCLUDED_FOUNDATIONS <= 40
    assert MAX_DISTANCE_FOUNDATIONS <= 20


def test_ensure_admin_creates_once_and_does_not_reset_the_password(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "free-admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "free-admin@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "local-pass-123")
    call_command("ensure_admin")
    user = get_user_model().objects.get(username="free-admin")
    assert user.is_superuser is True
    assert user.check_password("local-pass-123") is True
    user.set_password("changed-pass-123")
    user.save(update_fields=["password"])
    call_command("ensure_admin")
    user.refresh_from_db()
    assert user.check_password("changed-pass-123") is True


def test_a_second_solve_waits_outside_the_running_one():
    from apps.optimisation.services import runner

    assert runner._solve_lock.acquire(blocking=False) is True
    try:
        with pytest.raises(SolveBusy):
            execute(None)
    finally:
        runner._solve_lock.release()
