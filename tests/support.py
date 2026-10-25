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
