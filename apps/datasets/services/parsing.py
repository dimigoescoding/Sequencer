"""Parse the Information, Constraints, and Settings workbook.

Spreadsheet cells are untrusted data. Formula text is never calculated. When
Excel has already stored a calculated value, that stored value is read.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from apps.datasets.services.catalogue import (
    CompiledConstraint,
    ParsedSetting,
    compile_constraint,
    setting_key,
)
from apps.optimisation.services.types import FoundationInput

TRUE_TEXT = {"yes", "true", "1", "y"}
FALSE_TEXT = {"no", "false", "0", "n"}

HEADER_FIELDS = {
    "wtg id": "wtg_id",
    "structure": "structure",
    "easting": "easting",
    "northing": "northing",
    "aver weight": "weight",
    "spider location": "spider_location",
    "shallow location": "shallow_location",
    "string": "string",
    "jacking difficulty": "jacking_difficulty",
    "location": "location",
    "buffer iac-fou": "buffer_iac_fou",
    "buffer wtg-iac": "buffer_wtg_iac",
    "fou p50 start": "fou_p50_start",
    "fou p50 end": "fou_p50_end",
    "iac p50 start": "iac_p50_start",
    "iac p50 end": "iac_p50_end",
    "wtg p50 start": "wtg_p50_start",
    "wtg p50 end": "wtg_p50_end",
}

REQUIRED_FIELDS = (
    "wtg_id",
    "weight",
    "easting",
    "northing",
    "spider_location",
    "shallow_location",
    "jacking_difficulty",
)

FIELD_LABELS = {
    "wtg_id": "WTG ID",
    "weight": "Aver. Weight[t]",
    "easting": "Easting",
    "northing": "Northing",
    "spider_location": "Spider location",
    "shallow_location": "Shallow location",
    "jacking_difficulty": "Jacking difficulty",
    "location": "Location",
}

SOLVER_COLUMNS = {
    "wtg_id": "Foundation_ID",
    "weight": "Weight_t",
    "easting": "Easting_m",
    "northing": "Northing_m",
    "spider_location": "Spider location",
    "shallow_location": "Shallow location",
    "jacking_difficulty": "Jacking difficulty",
    "structure": "Structure",
    "string": "String",
    "location": "Location",
}


class UploadRejected(Exception):
    """The file cannot be stored as a dataset version."""


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    row_number: int | None = None
    column_name: str = ""


@dataclass
class ParseResult:
    foundations: list[FoundationInput] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    source_rows: list[int] = field(default_factory=list)
    constraints: list[CompiledConstraint] = field(default_factory=list)
    settings: list[ParsedSetting] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def parse_workbook(content: bytes) -> ParseResult:
    if _contains_macros(content):
        raise UploadRejected("Macro-enabled workbooks are not accepted and their code is not run.")
    try:
        formulas = load_workbook(BytesIO(content), data_only=False, keep_vba=False)
        cached = load_workbook(BytesIO(content), data_only=True, keep_vba=False)
    except Exception as exc:
        raise UploadRejected("The file is not a readable .xlsx workbook.") from exc

    information = _find_sheet(formulas, "information")
    constraints = _find_sheet(formulas, "constraints")
    settings = _find_sheet(formulas, "settings")
    issues: list[Issue] = []
    if information is None or constraints is None or settings is None:
        missing = [
            label
            for label, sheet in (
                ("Information", information),
                ("Constraints", constraints),
                ("Settings", settings),
            )
            if sheet is None
        ]
        issues.append(
            Issue(
                "error",
                "missing_sheet",
                "The workbook must contain Information, Constraints, and Settings sheets. Missing: "
                + ", ".join(missing)
                + ".",
            )
        )
        return ParseResult(issues=issues)

    cached_information = _find_sheet(cached, "information")
    foundations, source_rows, columns, row_issues = _parse_information(
        information, cached_information
    )
    issues.extend(row_issues)
    constraint_rows, constraint_issues = _parse_constraints(_find_sheet(formulas, "constraints"))
    issues.extend(constraint_issues)
    setting_rows, setting_issues = _parse_settings(_find_sheet(formulas, "settings"))
    issues.extend(setting_issues)
    if not foundations and not any(issue.code == "missing_columns" for issue in issues):
        issues.append(
            Issue(
                "error",
                "no_rows",
                "Information does not contain any location rows.",
            )
        )
    return ParseResult(
        foundations=foundations,
        issues=issues,
        columns=columns,
        source_rows=source_rows,
        constraints=constraint_rows,
        settings=setting_rows,
    )


def _contains_macros(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = [name.lower() for name in archive.namelist()]
    except zipfile.BadZipFile:
        return False
    return any(name.endswith("vbaproject.bin") for name in names)


def _find_sheet(workbook, expected: str) -> Worksheet | None:
    for name in workbook.sheetnames:
        if name.strip().casefold() == expected:
            return workbook[name]
    return None


def _header_key(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip().casefold()
    text = text.replace("[t]", "")
    text = text.replace("aver.", "aver")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return HEADER_FIELDS.get(text, "")


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_information(
    worksheet: Worksheet, cached: Worksheet | None
) -> tuple[list[FoundationInput], list[int], list[str], list[Issue]]:
    issues: list[Issue] = []
    header_row = next(worksheet.iter_rows(min_row=1, max_row=1))
    fields = [_header_key(cell.value) for cell in header_row]
    present = {name for name in fields if name}
    missing = [FIELD_LABELS[name] for name in REQUIRED_FIELDS if name not in present]
    columns = [SOLVER_COLUMNS[name] for name in present if name in SOLVER_COLUMNS]
    if missing:
        issues.append(
            Issue(
                "error",
                "missing_columns",
                "Mandatory columns are missing: " + ", ".join(missing) + ".",
            )
        )
        return [], [], columns, issues

    foundations: list[FoundationInput] = []
    source_rows: list[int] = []
    seen: set[str] = set()
    used_cached_formula = False
    for excel_row in worksheet.iter_rows(min_row=2):
        values: dict[str, Any] = {}
        empty = True
        row_number = excel_row[0].row
        formula_error = False
        for cell in excel_row:
            if cell.column - 1 >= len(fields):
                continue
            field_name = fields[cell.column - 1]
            if not field_name:
                continue
            cached_cell = cached.cell(cell.row, cell.column) if cached is not None else None
            value, kind = _read_cell(cell, cached_cell)
            if kind == "formula_missing":
                formula_error = True
                issues.append(
                    Issue(
                        "error",
                        "formula",
                        f"Row {cell.row} column {FIELD_LABELS.get(field_name, field_name)} contains a formula. "
                        "Sequencer does not calculate formulas. Save the workbook from Excel so the value is stored.",
                        row_number=cell.row,
                        column_name=FIELD_LABELS.get(field_name, field_name),
                    )
                )
                continue
            if kind == "cached":
                used_cached_formula = True
            if not _blank(value):
                empty = False
            values[field_name] = value
        if empty:
            continue
        identity = _text(values.get("wtg_id"))
        if identity.casefold().startswith("note"):
            continue
        if formula_error and identity == "":
            continue
        foundation, row_issues = _foundation_from_values(values, row_number, seen)
        issues.extend(row_issues)
        if foundation is not None:
            foundations.append(foundation)
            source_rows.append(row_number)
            seen.add(foundation.foundation_id.casefold())
    if used_cached_formula:
        issues.append(
            Issue(
                "warning",
                "cached_formula",
                "Some cells contain formulas. Sequencer used the values already stored in the workbook and did not calculate them.",
            )
        )
    return foundations, source_rows, columns, issues


def _read_cell(cell: Cell, cached: Cell | None) -> tuple[Any, str]:
    if cell.data_type == "f":
        if cached is None or cached.value is None:
            return None, "formula_missing"
        return cached.value, "cached"
    return cell.value, "value"


def _foundation_from_values(
    values: dict[str, Any], row_number: int, seen: set[str]
) -> tuple[FoundationInput | None, list[Issue]]:
    issues: list[Issue] = []
    foundation_id = _text(values.get("wtg_id"))
    if foundation_id == "":
        issues.append(
            Issue(
                "error",
                "missing_foundation_id",
                f"Row {row_number} is missing WTG ID.",
                row_number=row_number,
                column_name="WTG ID",
            )
        )
        return None, issues
    if foundation_id.casefold() in seen:
        issues.append(
            Issue(
                "error",
                "duplicate_foundation_id",
                f"WTG ID {foundation_id} is duplicated.",
                row_number=row_number,
                column_name="WTG ID",
            )
        )

    weight, weight_error = _decimal(values.get("weight"), positive=True)
    if weight_error:
        issues.append(
            Issue(
                "error",
                "invalid_weight",
                f"Row {row_number} Aver. Weight[t] must be a positive number.",
                row_number=row_number,
                column_name="Aver. Weight[t]",
            )
        )
    easting, east_error = _decimal(values.get("easting"), positive=False)
    northing, north_error = _decimal(values.get("northing"), positive=False)
    if east_error or north_error:
        issues.append(
            Issue(
                "error",
                "invalid_coordinate",
                f"Row {row_number} Easting and Northing must be numbers.",
                row_number=row_number,
                column_name="Easting",
            )
        )
    spider, spider_error = _boolean(values.get("spider_location"))
    shallow, shallow_error = _boolean(values.get("shallow_location"))
    if spider_error or shallow_error:
        issues.append(
            Issue(
                "error",
                "invalid_boolean",
                f"Row {row_number} Spider location and Shallow location must be Yes or No.",
                row_number=row_number,
                column_name="Spider location",
            )
        )
    difficulty = _text(values.get("jacking_difficulty"))
    if difficulty == "":
        issues.append(
            Issue(
                "error",
                "missing_difficulty",
                f"Row {row_number} is missing Jacking difficulty.",
                row_number=row_number,
                column_name="Jacking difficulty",
            )
        )
    location, location_error = _optional_int(values.get("location"))
    if location_error:
        issues.append(
            Issue(
                "error",
                "invalid_location",
                f"Row {row_number} Location must be a positive integer when provided.",
                row_number=row_number,
                column_name="Location",
            )
        )

    attributes: dict[str, Any] = {
        "Structure": _text(values.get("structure")),
        "Spider location": spider,
        "Shallow location": shallow,
        "String": _text(values.get("string")),
        "Jacking difficulty": difficulty,
        "Location": location,
    }
    for key, label in (
        ("buffer_iac_fou", "Buffer IAC-FOU"),
        ("buffer_wtg_iac", "Buffer WTG-IAC"),
        ("fou_p50_start", "FOU P50 start"),
        ("fou_p50_end", "FOU P50 end"),
        ("iac_p50_start", "IAC P50 start"),
        ("iac_p50_end", "IAC P50 end"),
        ("wtg_p50_start", "WTG P50 start"),
        ("wtg_p50_end", "WTG P50 end"),
    ):
        if key in values and not _blank(values.get(key)):
            attributes[label] = _json_ready(values.get(key))

    return (
        FoundationInput(
            foundation_id=foundation_id,
            include=True,
            weight_t=weight,
            easting_m=easting,
            northing_m=northing,
            attributes=attributes,
        ),
        issues,
    )


def _parse_constraints(worksheet: Worksheet | None) -> tuple[list[CompiledConstraint], list[Issue]]:
    if worksheet is None:
        return [], []
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return [], [Issue("error", "missing_columns", "The Constraints sheet has no header row.")]
    headers = [_plain_header(value) for value in rows[0]]
    indexes = {name: position for position, name in enumerate(headers) if name}
    required = ("package", "name", "explanation", "type", "severity", "status")
    missing = [name for name in required if name not in indexes]
    if missing:
        return [], [
            Issue(
                "error",
                "missing_columns",
                "The Constraints sheet is missing columns: " + ", ".join(missing) + ".",
            )
        ]
    compiled: list[CompiledConstraint] = []
    issues: list[Issue] = []
    order = 0
    for offset, row in enumerate(rows[1:], start=2):
        name = _cell_text(row, indexes["name"])
        if name == "" and _cell_text(row, indexes["package"]) == "":
            continue
        order += 1
        enforcement = _cell_text(row, indexes["type"]).casefold()
        status = _cell_text(row, indexes["status"]).casefold()
        if enforcement not in {"hard", "soft"}:
            issues.append(
                Issue(
                    "error",
                    "invalid_constraint",
                    f"Constraints row {offset} Type must be Hard or Soft.",
                    row_number=offset,
                    column_name="Type",
                )
            )
            enforcement = "hard"
        if status not in {"active", "not active"}:
            issues.append(
                Issue(
                    "error",
                    "invalid_constraint",
                    f"Constraints row {offset} Status must be Active or Not active.",
                    row_number=offset,
                    column_name="Status",
                )
            )
            status = "not active"
        reported = _cell_text(row, indexes["severity"]) or "NA"
        item = compile_constraint(
            package=_cell_text(row, indexes["package"]),
            name=name or f"Constraint {order}",
            explanation=_cell_text(row, indexes["explanation"]),
            enforcement=enforcement,
            reported_severity=reported,
            active=status == "active",
            source_row=offset,
        )
        if item.constraint_type == "unsupported":
            issues.append(
                Issue(
                    "warning",
                    "unsupported_constraint",
                    f"Constraint '{item.name}' is stored, but Sequencer has no solver rule for that name. "
                    "The explanation is not interpreted.",
                    row_number=offset,
                    column_name="Name",
                )
            )
        if item.enforcement == "soft" and item.severity is None:
            issues.append(
                Issue(
                    "error",
                    "invalid_severity",
                    f"Constraints row {offset} needs a severity for a soft constraint.",
                    row_number=offset,
                    column_name="Severity",
                )
            )
        compiled.append(item)
    if not compiled:
        issues.append(
            Issue(
                "warning",
                "no_constraints",
                "The Constraints sheet does not contain any constraint rows.",
            )
        )
    return compiled, issues


def _parse_settings(worksheet: Worksheet | None) -> tuple[list[ParsedSetting], list[Issue]]:
    if worksheet is None:
        return [], []
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return [], [Issue("error", "missing_columns", "The Settings sheet has no header row.")]
    headers = [_plain_header(value) for value in rows[0]]
    indexes = {name: position for position, name in enumerate(headers) if name}
    if "setting" not in indexes or "number" not in indexes:
        return [], [
            Issue(
                "error",
                "missing_columns",
                "The Settings sheet must contain Setting and Number columns.",
            )
        ]
    settings: list[ParsedSetting] = []
    issues: list[Issue] = []
    seen: set[str] = set()
    for offset, row in enumerate(rows[1:], start=2):
        name = _cell_text(row, indexes["setting"])
        if name == "":
            continue
        raw = row[indexes["number"]] if indexes["number"] < len(row) else None
        if _blank(raw):
            issues.append(
                Issue(
                    "error",
                    "missing_setting",
                    f"Settings row {offset} {name} has no number.",
                    row_number=offset,
                    column_name="Number",
                )
            )
            continue
        try:
            number = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            issues.append(
                Issue(
                    "error",
                    "invalid_setting",
                    f"Settings row {offset} {name} must be a number.",
                    row_number=offset,
                    column_name="Number",
                )
            )
            continue
        key = setting_key(name)
        if key in seen:
            issues.append(
                Issue(
                    "error",
                    "duplicate_setting",
                    f"Setting {name} is duplicated.",
                    row_number=offset,
                    column_name="Setting",
                )
            )
            continue
        seen.add(key)
        if key == "mp_per_trip" and (
            number != number.to_integral_value() or number < 1 or number > 20
        ):
            issues.append(
                Issue(
                    "error",
                    "invalid_setting",
                    f"Settings row {offset} MP per trip must be a whole number from 1 to 20.",
                    row_number=offset,
                    column_name="Number",
                )
            )
        settings.append(
            ParsedSetting(
                name=name,
                key=key,
                value=format(number, "f"),
                source_row=offset,
            )
        )
    if not settings:
        issues.append(
            Issue("warning", "no_settings", "The Settings sheet does not contain any settings.")
        )
    return settings, issues


def _plain_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _cell_text(row: tuple[Any, ...], index: int) -> str:
    if index >= len(row):
        return ""
    return _text(row[index])


def _text(value: Any) -> str:
    if _blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _boolean(value: Any) -> tuple[bool | None, bool]:
    if isinstance(value, bool):
        return value, False
    text = _text(value).casefold()
    if text in TRUE_TEXT:
        return True, False
    if text in FALSE_TEXT:
        return False, False
    return None, True


def _decimal(value: Any, *, positive: bool) -> tuple[Decimal | None, bool]:
    if _blank(value) or isinstance(value, bool):
        return None, True
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, True
    if not number.is_finite():
        return None, True
    if positive and number <= 0:
        return None, True
    return number.quantize(Decimal("0.001")), False


def _optional_int(value: Any) -> tuple[int | None, bool]:
    if _blank(value):
        return None, False
    if isinstance(value, bool):
        return None, True
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, True
    if number != number.to_integral_value() or number < 1:
        return None, True
    return int(number), False


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return format(Decimal(str(value)).quantize(Decimal("0.001")), "f")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    return _text(value)
