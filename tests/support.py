"""Small synthetic fixtures. These are not production project data."""

from __future__ import annotations

import zipfile
from decimal import Decimal
from io import BytesIO

from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig
from openpyxl import Workbook

HEADERS = [
    "Foundation_ID",
    "Include",
    "Weight_t",
    "Delivery_Sequence",
    "Length_m",
    "Delivery_Batch",
    "Easting_m",
    "Northing_m",
    "Punch_Through",
    "Difficulty_Value",
    "Notes",
]


INFO_HEADERS = [
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

DEFAULT_CONSTRAINTS = [
    (
        "FOU",
        "Spider locations FOU",
        "Spider locations should be installed first, but in no particular order.",
        "Hard",
        "NA",
        "Active",
    ),
    (
        "FOU",
        "Shallow locations",
        "Only one shallow location per trip allowed",
        "Hard",
        "NA",
        "Active",
    ),
    (
        "FOU",
        "Infield sailing optimization FOU",
        "Optimizes the infield sailing time within the trip from the given coordinates.",
        "Soft",
        0.5,
        "Active",
    ),
    (
        "FOU",
        "Jacking difficulty",
        "Avoid difficult locations in the first 3 trips",
        "Soft",
        0.5,
        "Not active",
    ),
]


def location_row(wtg: str, **overrides) -> dict:
    row = {
        "WTG ID": wtg,
        "Structure": "WTG",
        "Easting": 100,
        "Northing": 200,
        "Aver. Weight[t]": 100,
        "Spider location": "NO",
        "Shallow location": "NO",
        "String": "S1",
        "Jacking difficulty": "Easy",
        "Location": 1,
    }
    row.update(overrides)
    return row


def information_workbook(
    rows: list[dict],
    *,
    include_constraints: bool = True,
    include_settings: bool = True,
    settings: list[tuple] | None = None,
    constraints: list[tuple] | None = None,
) -> bytes:
    workbook = Workbook()
    information = workbook.active
    information.title = "Information"
    information.append(INFO_HEADERS)
    for row in rows:
        information.append([row.get(column) for column in INFO_HEADERS])
    if include_constraints:
        sheet = workbook.create_sheet("Constraints")
        sheet.append(["Package", "Name", "Explanation", "Type", "Severity", "Status"])
        for item in constraints or DEFAULT_CONSTRAINTS:
            sheet.append(list(item))
    if include_settings:
        sheet = workbook.create_sheet("Settings")
        sheet.append(["Setting", "Number"])
        for name, number in settings or [("MP per trip", 4)]:
            sheet.append([name, number])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def workbook_bytes(
    rows: list[dict], *, sheet: str = "Foundation_Input", headers: list[str] | None = None
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    used = headers or HEADERS
    worksheet.append(used)
    for row in rows:
        worksheet.append([row.get(column) for column in used])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def with_vba(content: bytes) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("xl/vbaProject.bin", b"macro")
    return output.getvalue()


def foundation(
    foundation_id: str,
    weight: str | int = 100,
    delivery: int | None = 1,
    *,
    include: bool = True,
    **kwargs,
) -> FoundationInput:
    return FoundationInput(
        foundation_id=foundation_id,
        include=include,
        weight_t=None if weight is None else Decimal(str(weight)),
        delivery_sequence=delivery,
        **kwargs,
    )


def vessel(**kwargs) -> VesselConfig:
    values = {
        "max_foundations_per_trip": 4,
        "allow_partial_final_trip": True,
        "solver_time_limit_seconds": 10,
    }
    values.update(kwargs)
    return VesselConfig(**values)


def constraint(
    name: str,
    constraint_type: str,
    parameters: dict,
    *,
    enforcement: str = "hard",
    severity: int | None = None,
    active: bool = True,
) -> ConstraintInput:
    return ConstraintInput(
        name=name,
        constraint_type=constraint_type,
        parameters=parameters,
        enforcement=enforcement,
        severity=severity,
        active=active,
    )


def valid_row(foundation_id: str = "F01", **overrides) -> dict:
    row = {
        "Foundation_ID": foundation_id,
        "Include": "Yes",
        "Weight_t": 120,
        "Delivery_Sequence": 1,
        "Length_m": 25,
        "Delivery_Batch": "A",
        "Easting_m": 1000,
        "Northing_m": 2000,
        "Punch_Through": "No",
        "Difficulty_Value": 10,
        "Notes": "Synthetic",
    }
    row.update(overrides)
    return row
