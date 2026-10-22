"""Downloadable workbook with the Information, Constraints, and Settings sheets.

The Information sheet has headings only. The constraint and setting rows are the
analysis catalogue. There is no project location data.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

INFORMATION_HEADERS = (
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
    "Buffer IAC-FOU",
    "Buffer WTG-IAC",
    "FOU P50 start",
    "FOU P50 end",
    "IAC P50 start",
    "IAC P50 end",
    "WTG P50 start",
    "WTG P50 end",
)

CONSTRAINT_ROWS = (
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
        "Optimizes the infield sailing time within the trip by calculating the distance between the turbines from the given coordinates",
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
)


def build_template() -> bytes:
    workbook = Workbook()
    information = workbook.active
    information.title = "Information"
    header_fill = PatternFill("solid", fgColor="0F2C4C")
    header_font = Font(color="FFFFFF", bold=True)
    for index, name in enumerate(INFORMATION_HEADERS, start=1):
        cell = information.cell(1, index, name)
        cell.fill = header_fill
        cell.font = header_font
        information.column_dimensions[get_column_letter(index)].width = max(18, len(name) + 2)
    information.freeze_panes = "A2"

    constraints = workbook.create_sheet("Constraints")
    for index, name in enumerate(
        ("Package", "Name", "Explanation", "Type", "Severity", "Status"), start=1
    ):
        cell = constraints.cell(1, index, name)
        cell.fill = header_fill
        cell.font = header_font
    for row_index, row in enumerate(CONSTRAINT_ROWS, start=2):
        for column, value in enumerate(row, start=1):
            constraints.cell(row_index, column, value)
    for column in range(1, 7):
        constraints.column_dimensions[get_column_letter(column)].width = 28

    settings = workbook.create_sheet("Settings")
    settings["A1"] = "Setting"
    settings["B1"] = "Number"
    settings["A1"].fill = header_fill
    settings["B1"].fill = header_fill
    settings["A1"].font = header_font
    settings["B1"].font = header_font
    settings["A2"] = "MP per trip"
    settings["B2"] = 4
    settings.column_dimensions["A"].width = 24

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
