"""Parse and validate a Foundation_Input workbook.

Spreadsheet cells are untrusted data. Formulas are rejected and never evaluated.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import Cell

from apps.datasets.columns import (
    ALL_COLUMNS,
    DECIMAL_COLUMNS,
    MANDATORY_COLUMNS,
    POSITIVE_DECIMAL_COLUMNS,
    POSITIVE_INT_COLUMNS,
)
from apps.optimisation.services.types import FoundationInput

TRUE_TEXT = {"yes", "true", "1", "y"}
FALSE_TEXT = {"no", "false", "0", "n"}


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

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def _blank(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _issue(
    severity: str, code: str, message: str, row: int | None = None, column: str = ""
) -> Issue:
    return Issue(severity=severity, code=code, message=message, row_number=row, column_name=column)


def _contains_macros(content: bytes) -> bool:
    """Reject workbooks that contain a VBA project. Cell values are never executed."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = [name.lower() for name in archive.namelist()]
    except zipfile.BadZipFile:
        return False
    return any(name.endswith("vbaproject.bin") for name in names)


def parse_workbook(content: bytes) -> ParseResult:
    if _contains_macros(content):
        raise UploadRejected("Macro-enabled workbooks are not accepted and their code is not run.")
    try:
        workbook = load_workbook(BytesIO(content), data_only=False, keep_vba=False)
    except Exception as exc:
        raise UploadRejected("The file is not a readable .xlsx workbook.") from exc
    if "Foundation_Input" not in workbook.sheetnames:
        return ParseResult(
            issues=[
                _issue(
                    "error",
                    "missing_sheet",
                    "The workbook must contain a sheet named Foundation_Input.",
                )
            ]
        )
    worksheet = workbook["Foundation_Input"]
    header_cells = [cell for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    headers = [_header_name(cell) for cell in header_cells]
    recognised = [name for name in headers if name in ALL_COLUMNS]
    missing = [name for name in MANDATORY_COLUMNS if name not in recognised]
    issues: list[Issue] = []
    unknown = [name for name in headers if name and name not in ALL_COLUMNS]
    if unknown:
        issues.append(
            _issue(
                "warning",
                "unknown_columns",
                "Unrecognised columns were ignored: " + ", ".join(unknown) + ".",
            )
        )
    if missing:
        issues.append(
            _issue(
                "error",
                "missing_columns",
                "Mandatory columns are missing: " + ", ".join(missing) + ".",
            )
        )
        return ParseResult(issues=issues, columns=recognised)

    raw_rows: list[dict[str, Any]] = []
    source_rows: list[int] = []
    for excel_row in worksheet.iter_rows(min_row=2):
        values: dict[str, Any] = {}
        formula = False
        empty = True
        for cell in excel_row:
            header = _header_name_from_index(headers, cell.column)
            if header not in ALL_COLUMNS:
                continue
            if cell.data_type == "f":
                formula = True
                issues.append(
                    _issue(
                        "error",
                        "formula",
                        f"Row {cell.row} column {header} contains a formula. "
                        "Formulas are not executed. Enter a calculated value.",
                        row=cell.row,
                        column=header,
                    )
                )
                values[header] = None
                empty = False
                continue
            if not _blank(cell.value):
                empty = False
            values[header] = cell.value
        if empty or (formula and not any(not _blank(value) for value in values.values())):
            continue
        raw_rows.append(values)
        source_rows.append(excel_row[0].row if excel_row else 0)

    frame = (
        pd.DataFrame(raw_rows, columns=list(ALL_COLUMNS))
        if raw_rows
        else pd.DataFrame(columns=list(ALL_COLUMNS))
    )
    if not frame.empty:
        frame = frame.where(pd.notna(frame), None)
    foundations, row_issues, kept_rows = _validate_frame(frame, source_rows, set(recognised))
    issues.extend(row_issues)
    if not foundations and not any(issue.code == "missing_columns" for issue in issues):
        issues.append(
            _issue(
                "error",
                "no_rows",
                "Foundation_Input does not contain any data rows.",
            )
        )
    return ParseResult(
        foundations=foundations,
        issues=issues,
        columns=recognised,
        source_rows=kept_rows,
    )


def _header_name(cell: Cell) -> str:
    if cell.value is None:
        return ""
    return str(cell.value).strip()


def _header_name_from_index(headers: list[str], column_index: int) -> str:
    position = column_index - 1
    if position < 0 or position >= len(headers):
        return ""
    return headers[position]


def _validate_frame(
    frame: pd.DataFrame,
    source_rows: list[int],
    columns_present: set[str],
) -> tuple[list[FoundationInput], list[Issue], list[int]]:
    issues: list[Issue] = []
    if frame.empty:
        return [], issues, []

    identifier_series = frame["Foundation_ID"].map(_text)
    duplicate_mask = identifier_series.duplicated(keep=False) & identifier_series.ne("")
    duplicate_ids = set(identifier_series[duplicate_mask].tolist())

    foundations: list[FoundationInput] = []
    kept_rows: list[int] = []
    for position, record in enumerate(frame.to_dict(orient="records")):
        excel_row = source_rows[position]
        foundation, row_issues, _included = _parse_record(
            record, excel_row, duplicate_ids, columns_present
        )
        issues.extend(row_issues)
        if foundation is not None:
            foundations.append(foundation)
            kept_rows.append(excel_row)

    _summary_warnings(foundations, columns_present, issues)
    return foundations, issues, kept_rows


def _summary_warnings(
    foundations: list[FoundationInput],
    columns_present: set[str],
    issues: list[Issue],
) -> None:
    included = [item for item in foundations if item.include]
    if not included:
        issues.append(
            _issue(
                "warning",
                "none_included",
                "No foundations are marked Include=Yes. Optimisation stays blocked until one is included.",
            )
        )
        return

    def missing(predicate) -> int:
        return sum(1 for item in included if predicate(item))

    if (
        "Easting_m" not in columns_present
        or "Northing_m" not in columns_present
        or missing(lambda item: item.easting_m is None or item.northing_m is None)
    ):
        issues.append(
            _issue(
                "warning",
                "missing_coordinates",
                "Coordinates are missing for one or more included foundations. "
                "Distance constraints stay unavailable. This warning does not block optimisation.",
            )
        )
    if "Difficulty_Value" not in columns_present or missing(
        lambda item: item.difficulty_value is None
    ):
        issues.append(
            _issue(
                "warning",
                "missing_difficulty",
                "Difficulty values are missing for one or more included foundations. "
                "Difficulty progression stays unavailable.",
            )
        )
    if "Delivery_Batch" not in columns_present or missing(lambda item: item.delivery_batch == ""):
        issues.append(
            _issue(
                "warning",
                "missing_delivery_batch",
                "Delivery batch is blank for one or more included foundations.",
            )
        )
    if "Notes" not in columns_present or missing(lambda item: item.notes == ""):
        issues.append(
            _issue(
                "warning",
                "missing_notes",
                "Notes are blank for one or more included foundations.",
            )
        )
    if "Delivery_Sequence" in columns_present and missing(
        lambda item: item.delivery_sequence is None
    ):
        issues.append(
            _issue(
                "warning",
                "missing_delivery_sequence",
                "Delivery sequence is blank for one or more included foundations. "
                "Delivery-order constraints stay unavailable while any included value is blank.",
            )
        )
    if "Punch_Through" not in columns_present or missing(lambda item: item.punch_through is None):
        if "Punch_Through" not in columns_present or any(
            item.punch_through is None for item in included
        ):
            issues.append(
                _issue(
                    "warning",
                    "missing_punch_through",
                    "Punch_Through is missing for one or more included foundations. "
                    "Rules that depend on Punch_Through cannot be checked for those rows.",
                )
            )


def _parse_record(
    record: dict[str, Any],
    excel_row: int,
    duplicate_ids: set[str],
    columns_present: set[str],
) -> tuple[FoundationInput | None, list[Issue], bool]:
    issues: list[Issue] = []
    foundation_id = _text(record.get("Foundation_ID"))
    if foundation_id == "":
        issues.append(
            _issue(
                "error",
                "missing_foundation_id",
                f"Row {excel_row} is missing Foundation_ID.",
                row=excel_row,
                column="Foundation_ID",
            )
        )
        return None, issues, False
    if foundation_id in duplicate_ids:
        issues.append(
            _issue(
                "error",
                "duplicate_foundation_id",
                f"Foundation_ID {foundation_id} is duplicated.",
                row=excel_row,
                column="Foundation_ID",
            )
        )

    include, include_error = _parse_bool(record.get("Include"), required=True)
    if include_error:
        issues.append(
            _issue(
                "error",
                "invalid_boolean",
                f"Row {excel_row} Include must be Yes/No, True/False, or 1/0.",
                row=excel_row,
                column="Include",
            )
        )
    punch_through = None
    if "Punch_Through" in columns_present and not _blank(record.get("Punch_Through")):
        punch_through, punch_error = _parse_bool(record.get("Punch_Through"), required=False)
        if punch_error:
            issues.append(
                _issue(
                    "error",
                    "invalid_boolean",
                    f"Row {excel_row} Punch_Through must be Yes/No, True/False, or 1/0.",
                    row=excel_row,
                    column="Punch_Through",
                )
            )

    weight, weight_error = _parse_decimal(record.get("Weight_t"), positive=True, required=True)
    if weight_error:
        issues.append(
            _issue(
                "error",
                "invalid_weight",
                f"Row {excel_row} Weight_t must be a positive number.",
                row=excel_row,
                column="Weight_t",
            )
        )

    integers: dict[str, int | None] = {}
    for column in POSITIVE_INT_COLUMNS:
        if column not in columns_present:
            integers[column] = None
            continue
        number, error = _parse_positive_int(record.get(column))
        integers[column] = number
        if error:
            issues.append(
                _issue(
                    "error",
                    "invalid_sequence",
                    f"Row {excel_row} {column} must be a positive integer when provided.",
                    row=excel_row,
                    column=column,
                )
            )
    earliest = integers.get("Earliest_Sequence")
    latest = integers.get("Latest_Sequence")
    if earliest is not None and latest is not None and earliest > latest:
        issues.append(
            _issue(
                "error",
                "earliest_after_latest",
                f"Row {excel_row} Earliest_Sequence cannot be greater than Latest_Sequence.",
                row=excel_row,
                column="Earliest_Sequence",
            )
        )

    decimals: dict[str, Decimal | None] = {}
    for column in DECIMAL_COLUMNS:
        if column == "Weight_t" or column not in columns_present:
            continue
        number, error = _parse_decimal(
            record.get(column), positive=column in POSITIVE_DECIMAL_COLUMNS
        )
        decimals[column] = number
        if error:
            issues.append(
                _issue(
                    "error",
                    "invalid_number",
                    f"Row {excel_row} {column} must be numeric when supplied.",
                    row=excel_row,
                    column=column,
                )
            )

    notes = ""
    if "Notes" in columns_present and not _blank(record.get("Notes")):
        notes = str(record.get("Notes")).strip()[:2000]
    batch = ""
    if "Delivery_Batch" in columns_present and not _blank(record.get("Delivery_Batch")):
        batch_value = record.get("Delivery_Batch")
        if isinstance(batch_value, float) and batch_value.is_integer():
            batch = str(int(batch_value))
        elif isinstance(batch_value, int) and not isinstance(batch_value, bool):
            batch = str(batch_value)
        else:
            batch = str(batch_value).strip()

    foundation = FoundationInput(
        foundation_id=foundation_id,
        include=bool(include),
        weight_t=weight,
        delivery_sequence=integers.get("Delivery_Sequence"),
        length_m=decimals.get("Length_m"),
        delivery_batch=batch,
        easting_m=decimals.get("Easting_m"),
        northing_m=decimals.get("Northing_m"),
        punch_through=punch_through,
        difficulty_value=decimals.get("Difficulty_Value"),
        eccentricity_limit_m=decimals.get("Eccentricity_Limit_m"),
        fixed_trip=integers.get("Fixed_Trip"),
        fixed_position=integers.get("Fixed_Position"),
        earliest_sequence=earliest,
        latest_sequence=latest,
        notes=notes,
    )
    return foundation, issues, bool(include)


def _text(value: Any) -> str:
    if _blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _parse_bool(value: Any, *, required: bool) -> tuple[bool | None, bool]:
    if _blank(value):
        return (None, True) if required else (None, False)
    if isinstance(value, bool):
        return value, False
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        if value == 1:
            return True, False
        if value == 0:
            return False, False
        return None, True
    text = str(value).strip().casefold()
    if text in TRUE_TEXT:
        return True, False
    if text in FALSE_TEXT:
        return False, False
    return None, True


def _parse_decimal(
    value: Any, *, positive: bool, required: bool = False
) -> tuple[Decimal | None, bool]:
    if _blank(value):
        return (None, True) if required else (None, False)
    if isinstance(value, bool):
        return None, True
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, True
    if not number.is_finite():
        return None, True
    if positive and number <= 0:
        return None, True
    return number, False


def _parse_positive_int(value: Any) -> tuple[int | None, bool]:
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
