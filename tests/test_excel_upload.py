"""Workbook upload and validation for the Information, Constraints, and Settings file."""

from pathlib import Path

import pytest
from apps.datasets.services.parsing import UploadRejected, parse_workbook
from apps.datasets.services.uploads import UploadRejected as StoredRejection
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.projects.models import Project
from django.contrib.auth import get_user_model
from openpyxl import Workbook
from tests.support import information_workbook, location_row, with_vba

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sequencer_input.xlsx"


def test_supplied_workbook_loads_locations_constraints_and_settings():
    parsed = parse_workbook(FIXTURE.read_bytes())
    assert parsed.error_count == 0
    assert len(parsed.foundations) == 50
    spiders = [
        item for item in parsed.foundations if item.attributes.get("Spider location") is True
    ]
    shallows = [
        item for item in parsed.foundations if item.attributes.get("Shallow location") is True
    ]
    assert len(spiders) == 10
    assert len(shallows) == 5
    assert parsed.foundations[0].foundation_id == "C06"
    assert parsed.foundations[0].weight_t is not None
    assert parsed.foundations[0].easting_m is not None
    names = [item.name for item in parsed.constraints]
    assert names == [
        "Spider locations FOU",
        "Shallow locations",
        "Infield sailing optimization FOU",
        "Jacking difficulty",
    ]
    by_name = {item.name: item for item in parsed.constraints}
    assert by_name["Spider locations FOU"].constraint_type == "matching_installed_first"
    assert by_name["Spider locations FOU"].active is True
    assert by_name["Spider locations FOU"].enforcement == "hard"
    assert by_name["Shallow locations"].parameters["maximum_count"] == 1
    assert by_name["Infield sailing optimization FOU"].severity == 50
    assert by_name["Infield sailing optimization FOU"].reported_severity == "0.5"
    assert by_name["Jacking difficulty"].active is False
    assert by_name["Jacking difficulty"].parameters["trip_count"] == 3
    assert parsed.settings[0].name == "MP per trip"
    assert parsed.settings[0].value == "4"
    assert any(issue.code == "cached_formula" for issue in parsed.issues)


def test_valid_workbook_parses_and_can_be_activated():
    user = get_user_model().objects.create_user(username="uploader", password="local-pass-123")
    project = Project.objects.create(owner=user, name="Upload", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=user,
        filename="locations.xlsx",
        content=information_workbook([location_row("A"), location_row("B", Location=2)]),
    )
    assert version.error_count == 0
    assert version.row_count == 2
    assert version.constraint_rows.count() == 4
    assert version.setting_rows.get().key == "mp_per_trip"
    activate_dataset(version)
    version.refresh_from_db()
    assert version.is_active is True


def test_missing_sheet_is_a_critical_error():
    content = information_workbook([location_row("A")], include_constraints=False)
    parsed = parse_workbook(content)
    assert parsed.error_count == 1
    assert parsed.issues[0].code == "missing_sheet"


def test_duplicate_foundation_id_is_an_error():
    parsed = parse_workbook(
        information_workbook([location_row("A"), location_row("A", Location=2)])
    )
    assert any(issue.code == "duplicate_foundation_id" for issue in parsed.issues)


def test_invalid_boolean_is_an_error():
    parsed = parse_workbook(
        information_workbook([location_row("A", **{"Spider location": "maybe"})])
    )
    assert any(issue.code == "invalid_boolean" for issue in parsed.issues)


def test_invalid_weight_is_an_error():
    parsed = parse_workbook(information_workbook([location_row("A", **{"Aver. Weight[t]": 0})]))
    assert any(issue.code == "invalid_weight" for issue in parsed.issues)


def test_invalid_dataset_cannot_be_activated():
    user = get_user_model().objects.create_user(username="blocked", password="local-pass-123")
    project = Project.objects.create(owner=user, name="Blocked", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=user,
        filename="bad.xlsx",
        content=information_workbook([location_row("A", **{"Aver. Weight[t]": "heavy"})]),
    )
    assert version.error_count > 0
    with pytest.raises(ValueError):
        activate_dataset(version)


def test_macro_workbook_is_rejected_without_execution():
    content = with_vba(information_workbook([location_row("A")]))
    with pytest.raises(UploadRejected):
        parse_workbook(content)
    with pytest.raises(StoredRejection):
        user = get_user_model().objects.create_user(username="macro", password="local-pass-123")
        project = Project.objects.create(owner=user, name="Macro", package_type="Foundation")
        create_dataset_version(project=project, user=user, filename="macro.xlsx", content=content)


def test_formula_without_a_stored_value_is_not_calculated():
    workbook = Workbook()
    information = workbook.active
    information.title = "Information"
    information.append(
        [
            "WTG ID",
            "Structure",
            "Easting",
            "Northing",
            "Aver. Weight[t]",
            "Spider location",
            "Shallow location",
            "String",
            "Jacking difficulty",
            "Location",
        ]
    )
    information.append(["A", "WTG", "=1+1", 10, 100, "NO", "NO", "S1", "Easy", 1])
    constraints = workbook.create_sheet("Constraints")
    constraints.append(["Package", "Name", "Explanation", "Type", "Severity", "Status"])
    settings = workbook.create_sheet("Settings")
    settings.append(["Setting", "Number"])
    settings.append(["MP per trip", 4])
    from io import BytesIO

    buffer = BytesIO()
    workbook.save(buffer)
    parsed = parse_workbook(buffer.getvalue())
    assert any(issue.code == "formula" for issue in parsed.issues)
    assert parsed.foundations == [] or parsed.foundations[0].easting_m is None
