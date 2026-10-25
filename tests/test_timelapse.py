"""The visual tab plots the sequence stored on the run."""

import pytest
from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.services.runner import execute
from apps.optimisation.services.timelapse import timelapse_payload
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.support import information_workbook, location_row

pytestmark = pytest.mark.django_db


def _run_with_coordinates():
    owner = get_user_model().objects.create_user(username="plotter", password="local-pass-123")
    project = Project.objects.create(owner=owner, name="Plot", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=owner,
        filename="plot.xlsx",
        content=information_workbook(
            [
                location_row("A", Easting=100, Northing=200),
                location_row("B", Easting=500, Northing=800, Location=2),
            ]
        ),
    )
    activate_dataset(version)
    scenario = Scenario.objects.create(
        project=project, name="Plot scenario", dataset_version=version
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
    return owner, execute(scenario)


def test_visual_tab_plots_the_stored_sequence(client):
    owner, run = _run_with_coordinates()
    client.force_login(owner)
    response = client.get(reverse("optimisation:detail", args=[run.pk]), {"tab": "visual"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "Easting/Northing · equal scale · no harbour or inter-trip legs" in body
    assert "52.347" not in body
    assert 'id="timelapse-play"' in body
    assert ">Pause<" in body
    assert "timelapse.js" in body
    assert '"id": "A"' in body
    assert '"id": "B"' in body
    assert "100.0" in body
    assert "500.0" in body
    assert "within-trip" in body


def test_same_trip_distance_is_captioned_and_a_trip_join_is_omitted():
    _owner, run = _run_with_coordinates()
    rows = list(run.sequence_rows.order_by("installation_sequence"))
    for row in rows:
        row.trip = 1
        row.save(update_fields=["trip"])
    same_trip = timelapse_payload(run)
    assert same_trip["within_trip"] == "0.389 nm"
    assert [frame["id"] for frame in same_trip["frames"]] == [row.foundation_id for row in rows]

    rows[1].trip = 2
    rows[1].save(update_fields=["trip"])
    joined = timelapse_payload(run)
    assert joined["within_trip"] == "0.000 nm"
    assert len(joined["frames"]) == 2


def test_visual_tab_names_foundations_without_coordinates(client):
    owner, run = _run_with_coordinates()
    foundation = run.dataset_version.foundations.get(foundation_id="B")
    foundation.northing_m = None
    foundation.save(update_fields=["northing_m"])
    client.force_login(owner)
    response = client.get(reverse("optimisation:detail", args=[run.pk]), {"tab": "visual"})
    body = response.content.decode()
    assert response.status_code == 200
    assert "no easting or northing" in body
    assert "B" in body
    assert "timelapse.js" not in body
    assert "52.347" not in body


def test_visual_tab_is_empty_when_no_sequence_was_stored(client):
    owner, run = _run_with_coordinates()
    run.sequence_rows.all().delete()
    client.force_login(owner)
    response = client.get(reverse("optimisation:detail", args=[run.pk]), {"tab": "visual"})
    body = response.content.decode()
    assert response.status_code == 200
    assert "nothing to plot" in body
    assert "timelapse.js" not in body
