"""Excel parsing and dataset-version rules."""

import pytest
from apps.datasets.services.parsing import UploadRejected, parse_workbook
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.projects.models import Project
from django.contrib.auth import get_user_model
from tests.support import valid_row, with_vba, workbook_bytes

pytestmark = pytest.mark.django_db


def test_valid_workbook_parses_and_can_be_activated():
    content = workbook_bytes(
        [valid_row("F01"), valid_row("F02", Include="No", Weight_t=80, Delivery_Sequence=2)]
    )
    parsed = parse_workbook(content)
    assert parsed.error_count == 0
    assert [item.foundation_id for item in parsed.foundations] == ["F01", "F02"]
    assert parsed.foundations[1].include is False

    user = get_user_model().objects.create_user(username="owner", password="local-pass-123")
    project = Project.objects.create(owner=user, name="Upload", package_type="Foundation")
    version = create_dataset_version(
        project=project, user=user, filename="foundations.xlsx", content=content
    )
    assert version.error_count == 0
    assert version.original_file.name.endswith(".xlsx")
    activate_dataset(version)
    version.refresh_from_db()
    assert version.is_active is True


def test_missing_sheet_is_a_critical_error():
    parsed = parse_workbook(workbook_bytes([valid_row()], sheet="Other"))
    assert parsed.error_count == 1
    assert parsed.issues[0].code == "missing_sheet"
    assert parsed.foundations == []


def test_missing_mandatory_columns_are_reported():
    parsed = parse_workbook(workbook_bytes([{"Foundation_ID": "F01"}], headers=["Foundation_ID"]))
    assert any(issue.code == "missing_columns" for issue in parsed.issues)
    assert parsed.foundations == []


def test_duplicate_foundation_id_is_an_error():
    parsed = parse_workbook(workbook_bytes([valid_row("F01"), valid_row("F01")]))
    assert any(issue.code == "duplicate_foundation_id" for issue in parsed.issues)


def test_invalid_boolean_is_an_error():
    parsed = parse_workbook(workbook_bytes([valid_row(Include="maybe")]))
    assert any(
        issue.code == "invalid_boolean" and issue.column_name == "Include"
        for issue in parsed.issues
    )


def test_invalid_weight_is_an_error():
    parsed = parse_workbook(workbook_bytes([valid_row(Weight_t=0)]))
    assert any(issue.code == "invalid_weight" for issue in parsed.issues)
    negative = parse_workbook(workbook_bytes([valid_row(Weight_t=-5)]))
    assert any(issue.code == "invalid_weight" for issue in negative.issues)


def test_earliest_greater_than_latest_is_an_error():
    content = workbook_bytes(
        [valid_row(Earliest_Sequence=8, Latest_Sequence=3)],
        headers=[*workbook_headers_with_window()],
    )
    parsed = parse_workbook(content)
    assert any(issue.code == "earliest_after_latest" for issue in parsed.issues)


def test_invalid_dataset_cannot_be_activated():
    user = get_user_model().objects.create_user(username="owner2", password="local-pass-123")
    project = Project.objects.create(owner=user, name="Broken", package_type="Foundation")
    version = create_dataset_version(
        project=project,
        user=user,
        filename="../odd name.xlsx",
        content=workbook_bytes([valid_row(Weight_t="heavy")]),
    )
    assert version.error_count > 0
    stored_name = version.original_file.name
    assert ".." not in stored_name
    assert stored_name.endswith(".xlsx")
    assert "odd_name" in stored_name
    with pytest.raises(ValueError):
        activate_dataset(version)


def test_macro_workbook_is_rejected_without_execution():
    content = with_vba(workbook_bytes([valid_row()]))
    with pytest.raises(UploadRejected, match="Macro-enabled"):
        parse_workbook(content)


def test_formula_cells_are_not_evaluated():
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Foundation_Input"
    worksheet.append(["Foundation_ID", "Include", "Weight_t", "Delivery_Sequence"])
    worksheet.append(["F01", "Yes", "=100+5", 1])
    buffer = BytesIO()
    workbook.save(buffer)
    parsed = parse_workbook(buffer.getvalue())
    assert any(issue.code == "formula" for issue in parsed.issues)
    assert parsed.foundations == [] or parsed.foundations[0].weight_t is None


def workbook_headers_with_window() -> list[str]:
    from tests.support import HEADERS

    return [*HEADERS, "Earliest_Sequence", "Latest_Sequence"]
