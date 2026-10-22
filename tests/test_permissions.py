"""A user can only open their own projects, scenarios, and exports."""

import pytest
from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.services.runner import execute
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.support import information_workbook, location_row

pytestmark = pytest.mark.django_db


def _owned_run():
    owner = get_user_model().objects.create_user(username="owner", password="local-pass-123")
    project = Project.objects.create(owner=owner, name="Private", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=owner,
        filename="private.xlsx",
        content=information_workbook([location_row("A"), location_row("B", Location=2)]),
    )
    activate_dataset(version)
    scenario = Scenario.objects.create(
        project=project, name="Private scenario", dataset_version=version
    )
    VesselSettings.objects.create(
        scenario=scenario, max_foundations_per_trip=2, solver_time_limit_seconds=10
    )
    Constraint.objects.create(
        scenario=scenario,
        name="Payload",
        constraint_type="maximum_trip_payload",
        enforcement="hard",
        active=True,
        parameters_json={"maximum_payload_t": "1000"},
        display_order=1,
    )
    run = execute(scenario)
    return owner, project, scenario, run


def test_other_user_cannot_open_project_scenario_or_export(client):
    _owner, project, scenario, run = _owned_run()
    outsider = get_user_model().objects.create_user(username="outsider", password="local-pass-123")
    client.force_login(outsider)
    project_url = reverse("projects:detail", args=[project.pk])
    scenario_url = reverse("scenarios:detail", args=[project.pk, scenario.pk])
    export_url = reverse("optimisation:export", args=[run.pk])
    assert client.get(project_url).status_code == 404
    assert client.get(scenario_url).status_code == 404
    assert client.get(export_url).status_code == 404


def test_owner_can_log_in_and_open_the_project(client):
    owner, project, scenario, run = _owned_run()
    logged_in = client.login(username="owner", password="local-pass-123")
    assert logged_in is True
    pages = [
        reverse("projects:detail", args=[project.pk]),
        reverse("datasets:index", args=[project.pk]),
        reverse("scenarios:list", args=[project.pk]),
        reverse("scenarios:detail", args=[project.pk, scenario.pk]),
        reverse("scenarios:settings", args=[project.pk, scenario.pk]),
        reverse("constraints:list", args=[project.pk, scenario.pk]),
        reverse("scenarios:generate", args=[project.pk, scenario.pk]),
        reverse("optimisation:detail", args=[run.pk]),
        reverse("optimisation:export", args=[run.pk]),
    ]
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
    assert owner.username == "owner"


def test_user_can_only_activate_or_deactivate_workbook_constraints(client):
    owner, project, scenario, _run = _owned_run()
    from apps.scenarios.services.sync import sync_scenario_from_dataset

    sync_scenario_from_dataset(scenario)
    client.force_login(owner)
    row = scenario.constraints.get(name="Jacking difficulty")
    assert row.active is False
    toggled = client.post(reverse("constraints:toggle", args=[project.pk, scenario.pk, row.pk]))
    assert toggled.status_code == 302
    row.refresh_from_db()
    assert row.active is True
    turned_off = client.post(reverse("constraints:toggle", args=[project.pk, scenario.pk, row.pk]))
    assert turned_off.status_code == 302
    row.refresh_from_db()
    assert row.active is False
    assert (
        client.get(f"/projects/{project.pk}/scenarios/{scenario.pk}/constraints/new/").status_code
        == 404
    )
    settings = client.get(reverse("scenarios:settings", args=[project.pk, scenario.pk]))
    assert settings.status_code == 200
    assert b"MP per trip" in settings.content
    assert b"Harbour" not in settings.content
    saved = client.post(
        reverse("scenarios:settings", args=[project.pk, scenario.pk]),
        {"value_0": "5"},
    )
    assert saved.status_code == 302
    scenario.vessel_settings.refresh_from_db()
    assert scenario.vessel_settings.max_foundations_per_trip == 5


def test_user_can_create_a_second_project(client):
    owner = get_user_model().objects.create_user(username="builder", password="local-pass-123")
    client.force_login(owner)
    first = client.post(reverse("projects:create"), {"name": "North", "description": "First"})
    second = client.post(reverse("projects:create"), {"name": "South", "description": "Second"})
    assert first.status_code == 302
    assert second.status_code == 302
    assert list(owner.projects.order_by("name").values_list("name", flat=True)) == [
        "North",
        "South",
    ]


def test_anonymous_user_is_sent_to_login(client):
    response = client.get(reverse("projects:list"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url
