"""Dedicated parameter validation for each constraint type."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.constraints.library import CONSTRAINT_TYPES
from apps.constraints.services.matching import (
    ALL_ATTRIBUTES,
    BOOLEAN_ATTRIBUTES,
    ORDERING_ATTRIBUTES,
    allowed_operators,
    as_decimal,
    parse_bool_token,
)
from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig

_FORMULA_PREFIXES = ("=",)


def _reject_formula(value: Any) -> str | None:
    if isinstance(value, str) and value.strip().startswith(_FORMULA_PREFIXES):
        return "Formulas are not accepted. Enter a literal value."
    return None


def _positive_decimal(value: Any, label: str) -> tuple[Decimal | None, str | None]:
    formula = _reject_formula(value)
    if formula:
        return None, formula
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, f"{label} must be a number."
    if number <= 0:
        return None, f"{label} must be greater than zero."
    return number, None


def _positive_int(value: Any, label: str) -> tuple[int | None, str | None]:
    formula = _reject_formula(value)
    if formula:
        return None, formula
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, f"{label} must be a positive integer."
    if number != number.to_integral_value() or number < 1:
        return None, f"{label} must be a positive integer."
    return int(number), None


def _non_negative_int(value: Any, label: str) -> tuple[int | None, str | None]:
    formula = _reject_formula(value)
    if formula:
        return None, formula
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, f"{label} must be an integer of zero or more."
    if number != number.to_integral_value() or number < 0:
        return None, f"{label} must be an integer of zero or more."
    return int(number), None


def _optional_decimal(value: Any, label: str) -> tuple[Decimal | None, str | None]:
    if value is None or value == "":
        return None, None
    formula = _reject_formula(value)
    if formula:
        return None, formula
    try:
        return Decimal(str(value)), None
    except (InvalidOperation, ValueError):
        return None, f"{label} must be a number."


def _foundation_id(value: Any, known: set[str]) -> str | None:
    if value is None or str(value).strip() == "":
        return "Select a foundation."
    text = str(value).strip()
    if text not in known:
        return f"Foundation {text} is not an included foundation in this dataset."
    return None


def _positions(value: Any, capacity: int, label: str) -> tuple[list[int] | None, str | None]:
    if not isinstance(value, list) or not value:
        return None, f"Select at least one {label}."
    positions: list[int] = []
    for item in value:
        number, error = _positive_int(item, label)
        if error or number is None:
            return None, error or f"{label} must be a positive integer."
        if number > capacity:
            return None, f"{label} {number} is above the vessel capacity of {capacity}."
        positions.append(number)
    unique = sorted(set(positions))
    if len(unique) != len(positions):
        return None, f"{label} contains duplicates."
    return unique, None


def _rule_errors(
    parameters: dict[str, Any],
    columns_present: set[str],
    *,
    require_attribute: bool,
) -> list[str]:
    errors: list[str] = []
    attribute = parameters.get("attribute")
    operator = parameters.get("operator")
    if not attribute:
        if require_attribute:
            errors.append("Select an attribute from the uploaded dataset.")
        return errors
    if attribute not in ALL_ATTRIBUTES:
        errors.append("The attribute is not part of the foundation dataset.")
        return errors
    if attribute not in columns_present and attribute not in {
        "Foundation_ID",
        "Include",
        "Weight_t",
    }:
        errors.append(
            f"{attribute} is not in this dataset. The rule cannot be used until the column is uploaded."
        )
        return errors
    if attribute == "Punch_Through" and "Punch_Through" not in columns_present:
        errors.append(
            "Punch-through rules require the Punch_Through column. "
            "This rule is unavailable because that column is missing."
        )
        return errors
    if operator not in allowed_operators(str(attribute)):
        errors.append(f"The operator {operator} cannot be used with {attribute}.")
        return errors
    if operator in {"is_blank", "is_not_blank"}:
        return errors
    value = parameters.get("value")
    formula = _reject_formula(value)
    if formula:
        errors.append(formula)
        return errors
    if operator == "between":
        upper_error = _reject_formula(parameters.get("value_to"))
        if upper_error:
            errors.append(upper_error)
        if as_decimal(value) is None or as_decimal(parameters.get("value_to")) is None:
            errors.append("Between requires two numeric bounds.")
    elif operator in {"in_list", "not_in_list"}:
        values = value if isinstance(value, list) else []
        if not values:
            errors.append(
                "Enter at least one list value. Separate values with commas. Do not enter a formula."
            )
        if attribute in BOOLEAN_ATTRIBUTES and any(
            parse_bool_token(item) is None for item in values
        ):
            errors.append("Boolean list values must be Yes/No, True/False, or 1/0.")
    elif attribute in BOOLEAN_ATTRIBUTES and parse_bool_token(value) is None:
        errors.append("Enter Yes/No, True/False, or 1/0.")
    elif attribute not in BOOLEAN_ATTRIBUTES | {"Foundation_ID", "Delivery_Batch", "Notes"}:
        if (
            operator
            in {
                "greater_than",
                "greater_than_or_equal",
                "less_than",
                "less_than_or_equal",
            }
            and as_decimal(value) is None
        ):
            errors.append("This operator requires a numeric comparison value.")
        elif value is None or str(value).strip() == "":
            errors.append("Enter a comparison value. This field is a literal, not a formula.")
    elif value is None or str(value).strip() == "":
        errors.append("Enter a comparison value. This field is a literal, not a formula.")
    return errors


def validate_parameters(
    constraint_type: str,
    parameters: dict[str, Any],
    *,
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    columns_present: set[str],
) -> list[str]:
    if constraint_type not in CONSTRAINT_TYPES:
        return ["This constraint type is not supported."]
    included_ids = {item.foundation_id for item in foundations if item.include}
    capacity = vessel.max_foundations_per_trip
    errors: list[str] = []

    if constraint_type == "maximum_trip_payload":
        _, error = _positive_decimal(parameters.get("maximum_payload_t"), "Maximum payload")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "fixed_trip":
        foundation_error = _foundation_id(parameters.get("foundation_id"), included_ids)
        if foundation_error:
            errors.append(foundation_error)
        _, error = _positive_int(parameters.get("trip_number"), "Trip number")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "fixed_vessel_position":
        foundation_error = _foundation_id(parameters.get("foundation_id"), included_ids)
        if foundation_error:
            errors.append(foundation_error)
        _, error = _positive_int(parameters.get("position_number"), "Position number")
        if error:
            errors.append(error)
        if parameters.get("trip_number") not in (None, ""):
            _, trip_error = _positive_int(parameters.get("trip_number"), "Trip number")
            if trip_error:
                errors.append(trip_error)
        return errors

    if constraint_type in {"allowed_positions", "excluded_positions"}:
        errors.extend(_rule_errors(parameters, columns_present, require_attribute=True))
        label = (
            "allowed position" if constraint_type == "allowed_positions" else "excluded position"
        )
        key = (
            "allowed_positions" if constraint_type == "allowed_positions" else "excluded_positions"
        )
        _, error = _positions(parameters.get(key), capacity, label)
        if error:
            errors.append(error)
        return errors

    if constraint_type in {"earliest_sequence", "latest_sequence"}:
        sequence_key = (
            "earliest_sequence" if constraint_type == "earliest_sequence" else "latest_sequence"
        )
        trip_key = "earliest_trip" if constraint_type == "earliest_sequence" else "latest_trip"
        has_foundation = bool(parameters.get("foundation_id"))
        has_attribute = bool(parameters.get("attribute"))
        if has_foundation == has_attribute:
            errors.append("Choose either one foundation or one attribute rule.")
        if has_foundation:
            foundation_error = _foundation_id(parameters.get("foundation_id"), included_ids)
            if foundation_error:
                errors.append(foundation_error)
        if has_attribute:
            errors.extend(_rule_errors(parameters, columns_present, require_attribute=True))
        has_sequence = parameters.get(sequence_key) not in (None, "")
        has_trip = parameters.get(trip_key) not in (None, "")
        if has_sequence == has_trip:
            errors.append("Set either a sequence position or a trip number, not both.")
        if has_sequence:
            _, error = _positive_int(parameters.get(sequence_key), "Sequence position")
            if error:
                errors.append(error)
        if has_trip:
            _, error = _positive_int(parameters.get(trip_key), "Trip number")
            if error:
                errors.append(error)
        return errors

    if constraint_type == "precedence":
        predecessor = parameters.get("predecessor_foundation_id")
        successor = parameters.get("successor_foundation_id")
        for label, value in (
            ("Predecessor", predecessor),
            ("Successor", successor),
        ):
            foundation_error = _foundation_id(value, included_ids)
            if foundation_error:
                errors.append(f"{label}: {foundation_error}")
        if predecessor and successor and str(predecessor) == str(successor):
            errors.append("Predecessor and successor must be different foundations.")
        _, error = _positive_int(parameters.get("minimum_gap"), "Minimum gap")
        if error:
            errors.append(error)
        if parameters.get("maximum_gap") not in (None, ""):
            maximum, max_error = _positive_int(parameters.get("maximum_gap"), "Maximum gap")
            minimum, _ = _positive_int(parameters.get("minimum_gap"), "Minimum gap")
            if max_error:
                errors.append(max_error)
            elif maximum is not None and minimum is not None and maximum < minimum:
                errors.append("Maximum gap cannot be less than minimum gap.")
        return errors

    if constraint_type == "maximum_matching_per_trip":
        errors.extend(_rule_errors(parameters, columns_present, require_attribute=True))
        _, error = _non_negative_int(parameters.get("maximum_count"), "Maximum count")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "minimum_matching_per_trip":
        errors.extend(_rule_errors(parameters, columns_present, require_attribute=True))
        _, error = _positive_int(parameters.get("minimum_count"), "Minimum count")
        if error:
            errors.append(error)
        trips = parameters.get("applicable_trips")
        if trips not in (None, "", []):
            if not isinstance(trips, list):
                errors.append("Applicable trips must be a list of trip numbers.")
            else:
                for trip in trips:
                    _, trip_error = _positive_int(trip, "Applicable trip")
                    if trip_error:
                        errors.append(trip_error)
                        break
        return errors

    if constraint_type in {"same_trip", "separate_trip"}:
        raw_ids = parameters.get("foundation_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) < 2:
            errors.append("Select at least two foundations.")
            return errors
        seen: set[str] = set()
        for item in raw_ids:
            foundation_error = _foundation_id(item, included_ids)
            if foundation_error:
                errors.append(foundation_error)
            elif str(item) in seen:
                errors.append(f"Foundation {item} is listed more than once.")
            else:
                seen.add(str(item))
        return errors

    if constraint_type == "attribute_ordering":
        attribute = parameters.get("attribute")
        if attribute not in ORDERING_ATTRIBUTES:
            errors.append("Attribute ordering requires a numeric dataset column.")
        elif attribute not in columns_present:
            errors.append(
                f"Attribute ordering on {attribute} requires that column in the uploaded dataset."
            )
        if parameters.get("direction") not in {"ascending", "descending"}:
            errors.append("Direction must be ascending or descending.")
        if parameters.get("scope") not in {"full_sequence", "within_trip"}:
            errors.append("Scope must be full_sequence or within_trip.")
        return errors

    if constraint_type == "delivery_sequence_alignment":
        if "Delivery_Sequence" not in columns_present:
            errors.append("Delivery-sequence alignment requires the Delivery_Sequence column.")
        _, error = _non_negative_int(parameters.get("tolerance_positions"), "Tolerance")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "difficulty_progression":
        attribute = parameters.get("attribute") or "Difficulty_Value"
        if attribute not in ORDERING_ATTRIBUTES:
            errors.append("Difficulty progression requires a numeric attribute.")
        elif attribute not in columns_present:
            errors.append(f"Difficulty progression requires {attribute} on the uploaded dataset.")
        _, start_error = _positive_int(parameters.get("applicable_start_trip"), "Start trip")
        _, end_error = _positive_int(parameters.get("applicable_end_trip"), "End trip")
        if start_error:
            errors.append(start_error)
        if end_error:
            errors.append(end_error)
        if (
            not start_error
            and not end_error
            and int(parameters["applicable_start_trip"]) > int(parameters["applicable_end_trip"])
        ):
            errors.append("The start trip cannot be after the end trip.")
        if parameters.get("direction") not in {"ascending", "descending"}:
            errors.append("Direction must be ascending or descending.")
        return errors

    if constraint_type == "matching_installed_first":
        return _rule_errors(parameters, columns_present, require_attribute=True)

    if constraint_type == "avoid_matching_in_first_trips":
        errors.extend(_rule_errors(parameters, columns_present, require_attribute=True))
        _, error = _positive_int(parameters.get("trip_count"), "Trip count")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "loop_id_sequence":
        if "Loop ID" not in columns_present:
            errors.append("Loop ID sequence requires the Loop ID column on the IAC sheet.")
        return errors

    if constraint_type == "string_id_sequence":
        if "String ID" not in columns_present:
            errors.append("String ID sequence requires the String ID column on the IAC sheet.")
        return errors

    if constraint_type == "package_buffer":
        mode = parameters.get("mode")
        if mode not in {"minimum", "maximize"}:
            errors.append("Choose a minimum number of days or maximize.")
            return errors
        if mode == "maximize":
            return errors
        _days, error = _non_negative_int(parameters.get("minimum_days"), "Minimum days")
        if error:
            errors.append(error)
        return errors

    if constraint_type == "minimise_within_trip_distance":
        if "Easting_m" not in columns_present or "Northing_m" not in columns_present:
            errors.append(
                "Distance constraints require Easting_m and Northing_m. "
                "This dataset does not include both columns."
            )
        include_harbour = bool(parameters.get("include_harbour_legs"))
        easting, east_error = _optional_decimal(
            parameters.get("harbour_easting_m"), "Harbour easting"
        )
        northing, north_error = _optional_decimal(
            parameters.get("harbour_northing_m"), "Harbour northing"
        )
        if east_error:
            errors.append(east_error)
        if north_error:
            errors.append(north_error)
        if include_harbour and (easting is None or northing is None):
            if vessel.harbour_easting_m is None or vessel.harbour_northing_m is None:
                errors.append(
                    "Harbour legs need harbour easting and northing on this constraint "
                    "or in the scenario vessel settings. No harbour default is applied."
                )
        return errors

    return ["This constraint type is not supported."]


def normalise_parameters(constraint: ConstraintInput) -> dict[str, Any]:
    """Return parameters with decimals preserved as strings for JSON storage."""
    cleaned: dict[str, Any] = {}
    for key, value in constraint.parameters.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        else:
            cleaned[key] = value
    return cleaned
