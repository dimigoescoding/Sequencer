"""Turn workbook constraint and setting rows into solver records.

The explanation text is stored and shown. It is not interpreted. Each supported
constraint is selected by its name. Unknown names are stored and are not given
a solver rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


def normalise_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def setting_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().casefold()).strip("_")


# Names from the workbook. The parameters are the rule those names denote.
NAMED_RULES: dict[str, dict[str, Any]] = {
    "spider locations fou": {
        "constraint_type": "matching_installed_first",
        "parameters": {
            "attribute": "Spider location",
            "operator": "equals",
            "value": "YES",
        },
    },
    "shallow locations": {
        "constraint_type": "maximum_matching_per_trip",
        "parameters": {
            "attribute": "Shallow location",
            "operator": "equals",
            "value": "YES",
            "maximum_count": 1,
        },
    },
    "infield sailing optimization fou": {
        "constraint_type": "minimise_within_trip_distance",
        "parameters": {"include_harbour_legs": False},
    },
    "jacking difficulty": {
        "constraint_type": "avoid_matching_in_first_trips",
        "parameters": {
            "attribute": "Jacking difficulty",
            "operator": "equals",
            "value": "Difficult",
            "trip_count": 3,
        },
    },
}


@dataclass
class CompiledConstraint:
    package: str
    name: str
    explanation: str
    enforcement: str
    severity: int | None
    reported_severity: str
    active: bool
    constraint_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    source_row: int | None = None


@dataclass
class ParsedSetting:
    name: str
    key: str
    value: str
    source_row: int | None = None


def compile_constraint(
    *,
    package: str,
    name: str,
    explanation: str,
    enforcement: str,
    reported_severity: str,
    active: bool,
    source_row: int | None,
) -> CompiledConstraint:
    rule = NAMED_RULES.get(normalise_name(name))
    if rule is None:
        return CompiledConstraint(
            package=package,
            name=name,
            explanation=explanation,
            enforcement=enforcement,
            severity=solver_severity(reported_severity) if enforcement == "soft" else None,
            reported_severity=reported_severity,
            active=active,
            constraint_type="unsupported",
            parameters={"reported_severity": reported_severity, "package": package},
            source_row=source_row,
        )
    parameters = dict(rule["parameters"])
    parameters["reported_severity"] = reported_severity
    parameters["package"] = package
    severity = solver_severity(reported_severity) if enforcement == "soft" else None
    return CompiledConstraint(
        package=package,
        name=name,
        explanation=explanation,
        enforcement=enforcement,
        severity=severity,
        reported_severity=reported_severity,
        active=active,
        constraint_type=rule["constraint_type"],
        parameters=parameters,
        source_row=source_row,
    )


def solver_severity(value: Any) -> int | None:
    """Map a workbook severity onto the solver's 1–100 scale.

    A value of 0.5 is half of the scale, so it becomes 50. Values already above
    1 are used as the 1–100 figure. Hard rows use NA and return None.
    """

    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in {"", "na", "n/a"}:
        return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if number <= 0:
        return None
    if number <= 1:
        scaled = int((number * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        scaled = int(number.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(100, max(1, scaled))
