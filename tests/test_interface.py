"""Small interface changes: scrolling foundations, shorter project tabs, generate progress."""

import pytest
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.support import information_workbook, location_row

pytestmark = pytest.mark.django_db


def _project():
    owner = get_user_model().objects.create_user(username="ui", password="local-pass-123")
    project = Project.objects.create(owner=owner, name="Interface", package_type="Foundation")
    rows = [location_row(f"F{index:02d}", Location=index) for index in range(1, 31)]
    version = create_dataset_version(
        project=project,
        user=owner,
        filename="rows.xlsx",
        content=information_workbook(rows),
    )
    activate_dataset(version)
    scenario = Scenario.objects.create(project=project, name="Main", dataset_version=version)
    VesselSettings.objects.create(scenario=scenario)
    return owner, project, scenario


def test_foundation_data_lists_every_row_in_a_scroll_panel(client):
    owner, project, _scenario = _project()
    client.force_login(owner)
    response = client.get(reverse("datasets:index", args=[project.pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert "foundation-scroll" in body
    assert 'aria-label="Pagination"' not in body
    for index in range(1, 31):
        assert f"F{index:02d}" in body


def test_project_tabs_omit_vessel_settings_and_optimisation_runs(client):
    owner, project, scenario = _project()
    client.force_login(owner)
    pages = [
        reverse("projects:detail", args=[project.pk]),
        reverse("datasets:index", args=[project.pk]),
        reverse("scenarios:list", args=[project.pk]),
        reverse("scenarios:detail", args=[project.pk, scenario.pk]),
        reverse("scenarios:generate", args=[project.pk, scenario.pk]),
    ]
    for url in pages:
        body = client.get(url).content.decode()
        assert ">Vessel Settings</a>" not in body
        assert ">Optimisation Runs</a>" not in body
        assert ">Scenarios</a>" in body


def test_generate_page_has_a_hidden_loading_bar(client):
    owner, project, scenario = _project()
    client.force_login(owner)
    body = client.get(reverse("scenarios:generate", args=[project.pk, scenario.pk])).content.decode()
    assert 'id="generate-progress"' in body
    assert "progress-bar-animated" in body
    assert "A sequence is running." in body
