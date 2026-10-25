"""Small synthetic fixtures. These are not production project data."""

from __future__ import annotations

import re
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


FOU_HEADERS = [
    "WTG ID",
    "Include",
    "Structure",
    "Easting",
    "Northing",
    "Aver. Weight[t]",
    "Spider location",
    "Shallow location",
    "Jacking Difficulty",
]
IAC_HEADERS = [
    "Cable ID",
    "Nickname",
    "Include",
    "String ID",
    "Loop ID",
    "Location ID (Cable start-point)",
    "Location ID (Cable end-point)",
    "Spider Cable",
]
WTG_HEADERS = [
    "WTG ID",
    "Include",
    "Structure",
    "Easting",
    "Northing",
    "Jacking difficulty WTG",
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
        "Include": "YES",
        "Structure": "WTG",
        "Easting": 100,
        "Northing": 200,
        "Aver. Weight[t]": 100,
        "Spider location": "NO",
        "Shallow location": "NO",
        "Jacking Difficulty": "Easy",
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
    omit: str | None = None,
    iac_rows: list[list] | None = None,
    wtg_rows: list[list] | None = None,
    extra_sheet: str | None = None,
) -> bytes:
    del include_constraints, include_settings, settings, constraints
    workbook = Workbook()
    fou = workbook.active
    fou.title = "FOU data"
    fou.append(FOU_HEADERS)
    for row in rows:
        fou.append([row.get(column) for column in FOU_HEADERS])
    iac = workbook.create_sheet("IAC data")
    iac.append(IAC_HEADERS)
    for row in iac_rows or []:
        iac.append(row)
    wtg = workbook.create_sheet("WTG data")
    wtg.append(WTG_HEADERS)
    for row in wtg_rows or []:
        wtg.append(row)
    programme = workbook.create_sheet("Programme")
    programme["B1"] = "FOU"
    programme["D1"] = "IAC"
    programme["F1"] = "WTG"
    programme.merge_cells("B1:C1")
    programme.merge_cells("D1:E1")
    programme.merge_cells("F1:G1")
    for index, name in enumerate(
        ("Location", "P50 Start", "P50 End", "P50 Start", "P50 End", "P50 Start", "P50 End"),
        start=1,
    ):
        programme.cell(2, index, name)
    if extra_sheet:
        workbook.create_sheet(extra_sheet)
    if omit and omit in workbook.sheetnames:
        workbook.remove(workbook[omit])
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
    package: str = "FOU",
) -> ConstraintInput:
    return ConstraintInput(
        name=name,
        constraint_type=constraint_type,
        parameters=parameters,
        enforcement=enforcement,
        severity=severity,
        active=active,
        package=package,
    )


def install_named_constraints(scenario) -> None:
    """Create the four former workbook rules on a scenario. They are not imported."""
    from apps.constraints.models import Constraint
    from apps.datasets.services.catalogue import compile_constraint

    for index, item in enumerate(DEFAULT_CONSTRAINTS, start=1):
        compiled = compile_constraint(
            package=item[0],
            name=item[1],
            explanation=item[2],
            enforcement=item[3].casefold(),
            reported_severity=str(item[4]),
            active=item[5].casefold() == "active",
            source_row=index,
        )
        Constraint.objects.create(
            scenario=scenario,
            name=compiled.name,
            constraint_type=compiled.constraint_type,
            description=compiled.explanation,
            active=compiled.active,
            enforcement=compiled.enforcement,
            severity=compiled.severity,
            package=compiled.package or "FOU",
            parameters_json=compiled.parameters,
            display_order=index,
        )


def legacy_campaign(path):
    """Read the older three-sheet fixture for the sailing-distance regression."""
    from pathlib import Path

    from apps.datasets.services.catalogue import compile_constraint
    from openpyxl import load_workbook

    workbook = load_workbook(Path(path), data_only=True)
    information = workbook["Information"]
    header = [_plain(cell.value) for cell in next(information.iter_rows(min_row=1, max_row=1))]
    index = {name: position for position, name in enumerate(header)}
    foundations = []
    for excel_row in information.iter_rows(min_row=2, values_only=True):
        identity = _cell(excel_row, index.get("wtg id"))
        if identity == "" or identity.casefold().startswith("note"):
            continue
        foundations.append(
            foundation(
                identity,
                _cell(excel_row, index["aver weight"]) or 0,
                None,
                easting_m=_number(excel_row, index["easting"]),
                northing_m=_number(excel_row, index["northing"]),
                attributes={
                    "Structure": _cell(excel_row, index.get("structure")),
                    "Spider location": _yes(excel_row, index.get("spider location")),
                    "Shallow location": _yes(excel_row, index.get("shallow location")),
                    "Jacking difficulty": _cell(excel_row, index.get("jacking difficulty")),
                    "String": _cell(excel_row, index.get("string")),
                },
            )
        )
    constraints_name = next(
        name for name in workbook.sheetnames if name.strip().casefold() == "constraints"
    )
    rules = []
    for offset, row in enumerate(
        workbook[constraints_name].iter_rows(min_row=2, values_only=True), start=2
    ):
        headers = [
            _plain(cell.value)
            for cell in next(workbook[constraints_name].iter_rows(min_row=1, max_row=1))
        ]
        positions = {name: position for position, name in enumerate(headers)}
        name = _cell(row, positions.get("name"))
        if name == "":
            continue
        compiled = compile_constraint(
            package=_cell(row, positions.get("package")) or "FOU",
            name=name,
            explanation=_cell(row, positions.get("explanation")),
            enforcement=_cell(row, positions.get("type")).casefold(),
            reported_severity=_cell(row, positions.get("severity")) or "NA",
            active=_cell(row, positions.get("status")).casefold() == "active",
            source_row=offset,
        )
        rules.append(
            ConstraintInput(
                name=compiled.name,
                constraint_type=compiled.constraint_type,
                parameters=compiled.parameters,
                enforcement=compiled.enforcement,
                active=compiled.active,
                severity=compiled.severity,
                description=compiled.explanation,
                package="FOU",
            )
        )
    return foundations, rules


def _plain(value) -> str:
    text = str(value or "").replace("\n", " ").strip().casefold()
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = text.replace("aver.", "aver")
    return re.sub(r"\s+", " ", text).strip(" .")


def _cell(row, index) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    value = row[index]
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _yes(row, index) -> bool | None:
    text = _cell(row, index).casefold()
    if text in {"yes", "true", "1", "y"}:
        return True
    if text in {"no", "false", "0", "n"}:
        return False
    return None


def _number(row, index):
    raw = row[index]
    if raw is None or raw == "":
        return None
    return Decimal(str(raw)).quantize(Decimal("0.001"))


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
