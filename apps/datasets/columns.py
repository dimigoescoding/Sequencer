"""Canonical Foundation_Input columns."""

from __future__ import annotations

MANDATORY_COLUMNS = (
    "Foundation_ID",
    "Include",
    "Weight_t",
    "Delivery_Sequence",
)

OPTIONAL_COLUMNS = (
    "Length_m",
    "Delivery_Batch",
    "Easting_m",
    "Northing_m",
    "Punch_Through",
    "Difficulty_Value",
    "Eccentricity_Limit_m",
    "Fixed_Trip",
    "Fixed_Position",
    "Earliest_Sequence",
    "Latest_Sequence",
    "Notes",
)

ALL_COLUMNS = MANDATORY_COLUMNS + OPTIONAL_COLUMNS

BOOLEAN_COLUMNS = {"Include", "Punch_Through"}
POSITIVE_INT_COLUMNS = {
    "Delivery_Sequence",
    "Fixed_Trip",
    "Fixed_Position",
    "Earliest_Sequence",
    "Latest_Sequence",
}
DECIMAL_COLUMNS = {
    "Weight_t",
    "Length_m",
    "Easting_m",
    "Northing_m",
    "Difficulty_Value",
    "Eccentricity_Limit_m",
}
POSITIVE_DECIMAL_COLUMNS = {"Weight_t"}
