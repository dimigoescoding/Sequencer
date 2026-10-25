"""The visual tab plots FOU and WTG on one programme calendar."""

from datetime import UTC, datetime, timedelta

import pytest
from apps.constraints.models import Constraint
from apps.datasets.models import ProgrammeSlot, WtgLocation
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.models import SequenceResult
from apps.optimisation.services.runner import execute
from apps.optimisation.services.timelapse import timelapse_payload
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.support import information_workbook, location_row

pytestmark = pytest.mark.django_db


def _add_fou_dates(run):
    start = datetime(2030, 4, 1, tzinfo=UTC)
    for row in run.sequence_rows.all():
        if (row.package or "FOU") != "FOU":
            continue
        ProgrammeSlot.objects.create(
            dataset_version=run.dataset_version,
            slot=row.installation_sequence,
            fou_p50_start=start + timedelta(days=row.installation_sequence - 1),
            fou_p50_end=start + timedelta(days=row.installation_sequence),
        )


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
    owner_run = owner, execute(scenario)
    _add_fou_dates(owner_run[1])
    return owner_run


def test_visual_tab_plots_the_stored_sequence(client):
    owner, run = _run_with_coordinates()
    client.force_login(owner)
    response = client.get(reverse("optimisation:detail", args=[run.pk]), {"tab": "visual"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "calendar time" in body
    assert "circle FOU" in body
    assert "square WTG" in body
    assert "52.347" not in body
    assert 'id="timelapse-play"' in body
    assert ">Pause<" in body
    assert "timelapse.js" in body
    assert '"id": "A"' in body
    assert '"id": "B"' in body
    assert "100.0" in body
    assert "500.0" in body
    assert "within-trip" in body
    payload = timelapse_payload(run)
    assert payload["player"]["origin"] == int(datetime(2030, 4, 1, tzinfo=UTC).timestamp() * 1000)


def test_same_trip_distance_is_captioned_and_a_trip_join_is_omitted():
    _owner, run = _run_with_coordinates()
    rows = list(run.sequence_rows.order_by("installation_sequence"))
    for row in rows:
        row.trip = 1
        row.save(update_fields=["trip"])
    same_trip = timelapse_payload(run)
    assert same_trip["within_trip"] == "FOU 0.389 nm"
    assert [frame["id"] for frame in same_trip["activities"]] == [row.foundation_id for row in rows]

    rows[1].trip = 2
    rows[1].save(update_fields=["trip"])
    joined = timelapse_payload(run)
    assert joined["within_trip"] == "FOU 0.000 nm"
    assert len(joined["activities"]) == 2


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


def test_wtg_uses_its_own_dates_and_coordinates():
    _owner, run = _run_with_coordinates()
    dataset = run.dataset_version
    WtgLocation.objects.create(
        dataset_version=dataset, wtg_id="A", include=True, easting_m=110, northing_m=210
    )
    WtgLocation.objects.create(
        dataset_version=dataset, wtg_id="B", include=True, easting_m=510, northing_m=810
    )
    for sequence, foundation_id in ((1, "A"), (2, "B")):
        SequenceResult.objects.create(
            run=run,
            package="WTG",
            installation_sequence=sequence,
            trip=1,
            vessel_position=sequence,
            foundation_id=foundation_id,
            hard_constraint_status="Passed",
        )
    SequenceResult.objects.create(
        run=run,
        package="IAC",
        installation_sequence=1,
        trip=1,
        vessel_position=1,
        foundation_id="C1",
        hard_constraint_status="Passed",
    )
    fou_rows = list(run.sequence_rows.filter(package="FOU").order_by("installation_sequence"))
    fou_rows[0].trip = 1
    fou_rows[1].trip = 2
    fou_rows[0].save(update_fields=["trip"])
    fou_rows[1].save(update_fields=["trip"])
    wtg_start = datetime(2031, 3, 1, tzinfo=UTC)
    for slot in dataset.programme_slots.all():
        slot.wtg_p50_start = wtg_start + timedelta(days=(slot.slot - 1) * 4)
        slot.wtg_p50_end = wtg_start + timedelta(days=slot.slot * 4)
        slot.save()
    payload = timelapse_payload(run)
    fou = [item for item in payload["activities"] if item["package"] == "FOU"]
    wtg = [item for item in payload["activities"] if item["package"] == "WTG"]
    assert {item["id"] for item in fou} == {"A", "B"}
    assert [item["id"] for item in wtg] == ["A", "B"]
    assert all(item["marker"] == "circle" for item in fou)
    assert all(item["marker"] == "square" for item in wtg)
    assert wtg[0]["x"] == 110.0
    assert wtg[0]["start"] == int(wtg_start.timestamp() * 1000)
    assert wtg[0]["start"] > fou[-1]["end"]
    assert "C1" not in {item["id"] for item in payload["activities"]}
    assert payload["within_trip"] == "FOU 0.000 nm · WTG 0.389 nm"


def test_a_partial_programme_calendar_is_not_plotted():
    _owner, run = _run_with_coordinates()
    slot = run.dataset_version.programme_slots.order_by("slot").last()
    slot.fou_p50_end = None
    slot.save(update_fields=["fou_p50_end"])
    payload = timelapse_payload(run)
    assert payload["activities"] == []
    assert payload["player"] is None
    assert "do not cover every sequenced" in payload["notice"]
    assert "FOU 1/2" in payload["notice"]


def test_a_sequence_without_programme_dates_is_not_plotted():
    _owner, run = _run_with_coordinates()
    run.dataset_version.programme_slots.all().delete()
    payload = timelapse_payload(run)
    assert payload["activities"] == []
    assert "no programme dates" in payload["notice"]


def test_visual_tab_is_empty_when_no_sequence_was_stored(client):
    owner, run = _run_with_coordinates()
    run.sequence_rows.all().delete()
    client.force_login(owner)
    response = client.get(reverse("optimisation:detail", args=[run.pk]), {"tab": "visual"})
    body = response.content.decode()
    assert response.status_code == 200
    assert "nothing to plot" in body
    assert "timelapse.js" not in body
