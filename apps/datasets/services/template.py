"""Downloadable Foundation_Input template. It contains no project data."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.datasets.columns import ALL_COLUMNS

_NOTES = {
    "Foundation_ID": "Required. Unique text identifier.",
    "Include": "Required. Yes/No, True/False, or 1/0.",
    "Weight_t": "Required. Positive number. No default is applied.",
    "Delivery_Sequence": "Column required. Value optional. Positive integer when provided.",
    "Length_m": "Optional number. Leave blank for null.",
    "Delivery_Batch": "Optional. Leave blank for null.",
    "Easting_m": "Optional number. Required only if you add distance constraints.",
    "Northing_m": "Optional number. Required only if you add distance constraints.",
    "Punch_Through": "Optional. Yes/No, True/False, or 1/0. Leave blank for null.",
    "Difficulty_Value": "Optional number. Required only for difficulty progression.",
    "Eccentricity_Limit_m": "Optional number.",
    "Fixed_Trip": "Optional positive integer. Stored as data. Add a constraint to enforce it.",
    "Fixed_Position": "Optional positive integer. Checked against vessel capacity before solving.",
    "Earliest_Sequence": "Optional positive integer. Cannot exceed Latest_Sequence.",
    "Latest_Sequence": "Optional positive integer.",
    "Notes": "Optional text. Formulas are rejected.",
}


def build_template() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Foundation_Input"
    header_fill = PatternFill("solid", fgColor="0F2C4C")
    header_font = Font(color="FFFFFF", bold=True)
    for index, name in enumerate(ALL_COLUMNS, start=1):
        cell = worksheet.cell(1, index, name)
        cell.fill = header_fill
        cell.font = header_font
        cell.comment = Comment(_NOTES.get(name, ""), "Sequencer", width=240, height=60)
        worksheet.column_dimensions[get_column_letter(index)].width = max(18, len(name) + 2)
    worksheet.auto_filter.ref = f"A1:{get_column_letter(len(ALL_COLUMNS))}1"
    worksheet.freeze_panes = "A2"
    worksheet.sheet_view.showGridLines = True
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
