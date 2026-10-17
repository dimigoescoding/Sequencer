"""A user can only open their own projects, scenarios, and exports."""

import pytest
from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.services.runner import execute
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.support import valid_row, workbook_bytes

pytestmark = pytest.mark.django_db


def _owned_run():
    owner = get_user_model().objects.create_user(username="owner", password="local-pass-123")
    project = Project.objects.create(owner=owner, name="Private", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=owner,
        filename="private.xlsx",
        content=workbook_bytes([valid_row("A"), valid_row("B", Delivery_Sequence=2)]),
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
        reverse("constraints:choose", args=[project.pk, scenario.pk]),
        reverse("scenarios:generate", args=[project.pk, scenario.pk]),
        reverse("optimisation:detail", args=[run.pk]),
        reverse("optimisation:export", args=[run.pk]),
    ]
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
    assert owner.username == "owner"


def test_user_can_add_edit_and_remove_a_soft_constraint(client):
    owner, project, scenario, _run = _owned_run()
    client.force_login(owner)
    create_url = reverse(
        "constraints:create",
        args=[project.pk, scenario.pk, "delivery_sequence_alignment"],
    )
    created = client.post(
        create_url,
        {
            "name": "Stay near delivery",
            "description": "User-entered preference.",
            "enforcement": "soft",
            "severity": "80",
            "active": "on",
            "tolerance_positions": "1",
        },
    )
    assert created.status_code == 302
    row = scenario.constraints.get(name="Stay near delivery")
    assert row.enforcement == "soft"
    assert row.severity == 80
    edited = client.post(
        reverse("constraints:edit", args=[project.pk, scenario.pk, row.pk]),
        {
            "name": "Stay near delivery",
            "description": "Now mandatory.",
            "enforcement": "hard",
            "severity": "80",
            "active": "on",
            "tolerance_positions": "1",
        },
    )
    assert edited.status_code == 302
    row.refresh_from_db()
    assert row.enforcement == "hard"
    assert row.severity is None
    duplicated = client.post(
        reverse("constraints:duplicate", args=[project.pk, scenario.pk, row.pk])
    )
    assert duplicated.status_code == 302
    copy = scenario.constraints.get(name="Stay near delivery (copy)")
    assert copy.enforcement == "hard"
    toggled = client.post(reverse("constraints:toggle", args=[project.pk, scenario.pk, copy.pk]))
    assert toggled.status_code == 302
    copy.refresh_from_db()
    assert copy.active is False
    deleted = client.post(reverse("constraints:delete", args=[project.pk, scenario.pk, copy.pk]))
    assert deleted.status_code == 302
    assert not scenario.constraints.filter(pk=copy.pk).exists()


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
