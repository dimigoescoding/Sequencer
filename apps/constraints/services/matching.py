"""Attribute comparisons for the controlled rule builder.

Values are compared as data. Nothing in this module is evaluated as code.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.optimisation.services.types import FoundationInput

BOOLEAN_ATTRIBUTES = {"Include", "Punch_Through", "Spider location", "Shallow location"}
NUMERIC_ATTRIBUTES = {
    "Weight_t",
    "Delivery_Sequence",
    "Length_m",
    "Easting_m",
    "Northing_m",
    "Difficulty_Value",
    "Eccentricity_Limit_m",
    "Fixed_Trip",
    "Fixed_Position",
    "Earliest_Sequence",
    "Latest_Sequence",
    "Location",
}
STRING_ATTRIBUTES = {
    "Foundation_ID",
    "Delivery_Batch",
    "Notes",
    "Jacking difficulty",
    "String",
    "Structure",
}
ALL_ATTRIBUTES = BOOLEAN_ATTRIBUTES | NUMERIC_ATTRIBUTES | STRING_ATTRIBUTES

OPERATORS = (
    "equals",
    "does_not_equal",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "between",
    "in_list",
    "not_in_list",
    "is_blank",
    "is_not_blank",
)
NUMERIC_OPERATORS = {
    "equals",
    "does_not_equal",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "between",
    "in_list",
    "not_in_list",
    "is_blank",
    "is_not_blank",
}
BOOLEAN_OPERATORS = {
    "equals",
    "does_not_equal",
    "in_list",
    "not_in_list",
    "is_blank",
    "is_not_blank",
}
STRING_OPERATORS = {
    "equals",
    "does_not_equal",
    "in_list",
    "not_in_list",
    "is_blank",
    "is_not_blank",
}

ATTRIBUTE_FIELDS = {
    "Foundation_ID": "foundation_id",
    "Include": "include",
    "Weight_t": "weight_t",
    "Delivery_Sequence": "delivery_sequence",
    "Length_m": "length_m",
    "Delivery_Batch": "delivery_batch",
    "Easting_m": "easting_m",
    "Northing_m": "northing_m",
    "Punch_Through": "punch_through",
    "Difficulty_Value": "difficulty_value",
    "Eccentricity_Limit_m": "eccentricity_limit_m",
    "Fixed_Trip": "fixed_trip",
    "Fixed_Position": "fixed_position",
    "Earliest_Sequence": "earliest_sequence",
    "Latest_Sequence": "latest_sequence",
    "Notes": "notes",
}

ORDERING_ATTRIBUTES = (
    "Weight_t",
    "Delivery_Sequence",
    "Length_m",
    "Difficulty_Value",
    "Eccentricity_Limit_m",
    "Easting_m",
    "Northing_m",
)


def attribute_value(foundation: FoundationInput, attribute: str) -> Any:
    if attribute in ATTRIBUTE_FIELDS:
        return getattr(foundation, ATTRIBUTE_FIELDS[attribute])
    return foundation.attributes.get(attribute)


def is_blank(value: Any) -> bool:
    return value is None or value == ""


def parse_bool_token(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"yes", "true", "1", "y"}:
        return True
    if text in {"no", "false", "0", "n"}:
        return False
    return None


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool):
        parsed = parse_bool_token(expected)
        return parsed is not None and actual is parsed
    left = as_decimal(actual)
    right = as_decimal(expected)
    if left is not None and right is not None:
        return left == right
    return str(actual).strip().casefold() == str(expected).strip().casefold()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None or value == "":
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def matches(foundation: FoundationInput, parameters: dict[str, Any]) -> bool:
    attribute = parameters.get("attribute")
    operator = parameters.get("operator")
    if not attribute or not operator:
        return False
    actual = attribute_value(foundation, attribute)
    if operator == "is_blank":
        return is_blank(actual)
    if operator == "is_not_blank":
        return not is_blank(actual)
    if is_blank(actual):
        return False
    expected = parameters.get("value")
    if operator == "equals":
        return values_equal(actual, expected)
    if operator == "does_not_equal":
        return not values_equal(actual, expected)
    if operator in {"in_list", "not_in_list"}:
        found = any(values_equal(actual, item) for item in _as_list(expected))
        return found if operator == "in_list" else not found
    left = as_decimal(actual)
    right = as_decimal(expected)
    upper = as_decimal(parameters.get("value_to"))
    if left is None or right is None:
        return False
    if operator == "greater_than":
        return left > right
    if operator == "greater_than_or_equal":
        return left >= right
    if operator == "less_than":
        return left < right
    if operator == "less_than_or_equal":
        return left <= right
    if operator == "between":
        if upper is None:
            return False
        low, high = (right, upper) if right <= upper else (upper, right)
        return low <= left <= high
    return False


def matching_foundations(
    foundations: list[FoundationInput], parameters: dict[str, Any]
) -> list[FoundationInput]:
    included = [item for item in foundations if item.include]
    if parameters.get("foundation_id") and not parameters.get("attribute"):
        wanted = str(parameters["foundation_id"])
        return [item for item in included if item.foundation_id == wanted]
    if parameters.get("attribute"):
        matched = [item for item in included if matches(item, parameters)]
        if parameters.get("foundation_id"):
            wanted = str(parameters["foundation_id"])
            matched = [item for item in matched if item.foundation_id == wanted]
        return matched
    if parameters.get("foundation_ids"):
        wanted = {str(item) for item in parameters["foundation_ids"]}
        return [item for item in included if item.foundation_id in wanted]
    return []


def column_state(
    foundations: list[FoundationInput], columns_present: set[str]
) -> dict[str, dict[str, bool]]:
    included = [item for item in foundations if item.include]
    state: dict[str, dict[str, bool]] = {}
    for attribute in ALL_ATTRIBUTES:
        values = [attribute_value(item, attribute) for item in included]
        populated = [value for value in values if not is_blank(value)]
        state[attribute] = {
            "present": attribute in columns_present,
            "any": bool(populated),
            "complete": bool(included) and len(populated) == len(included),
        }
    return state


def allowed_operators(attribute: str) -> set[str]:
    if attribute in BOOLEAN_ATTRIBUTES:
        return set(BOOLEAN_OPERATORS)
    if attribute in NUMERIC_ATTRIBUTES:
        return set(NUMERIC_OPERATORS)
    return set(STRING_OPERATORS)
