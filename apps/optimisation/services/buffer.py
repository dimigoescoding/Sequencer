"""Programme-day gap between one package and the previous package at a location.

IAC waits for the FOU end. WTG waits for IAC. A location's IAC starts when the
first cable that touches it starts, and it is complete when every such cable
is complete. Locations missing from the previous package are left out. Dates
are the programme slot of the sequence position. This module does not read
solver assertions.
"""

from __future__ import annotations

from datetime import datetime

from apps.optimisation.services.scaling import scaled_penalty
from apps.optimisation.services.types import (
    CampaignResult,
    ConstraintInput,
    Evaluation,
    FoundationInput,
    ValidationRow,
)

DAY_SECONDS = 86400
PREVIOUS = {"IAC": "FOU", "WTG": "IAC"}


def package_name(constraint: ConstraintInput) -> str:
    package = str(getattr(constraint, "package", "") or "FOU").strip().upper()
    if package not in {"FOU", "IAC", "WTG"}:
        return "FOU"
    return package


def endpoint_keys(item: FoundationInput) -> set[str]:
    keys = {
        str(item.attributes.get("Start location", "")).strip().casefold(),
        str(item.attributes.get("End location", "")).strip().casefold(),
    }
    keys.discard("")
    return keys


def location_links(
    later: str, groups: dict[str, list[FoundationInput]]
) -> list[tuple[str, list[int], list[int]]]:
    """Pairs for one waiting package. Indexes refer to the included lists in groups."""
    earlier = PREVIOUS[later]
    if later == "IAC":
        places = groups.get("FOU", [])
        cables = groups.get("IAC", [])
        links = []
        for index, place in enumerate(places):
            touched = _touching(cables, place.foundation_id)
            if touched:
                links.append((place.foundation_id, [index], touched))
        return links
    places = groups.get("WTG", [])
    cables = groups.get("IAC", [])
    links = []
    for index, place in enumerate(places):
        touched = _touching(cables, place.foundation_id)
        if touched:
            links.append((place.foundation_id, touched, [index]))
    return links


def slot_instants(
    calendar: dict, package: str, count: int, edge: str
) -> list[int] | None:
    values = []
    for position in range(1, count + 1):
        window = calendar.get(position, {}).get(package)
        if not window:
            return None
        value = window[0] if edge == "start" else window[1]
        if value is None:
            return None
        values.append(instant_seconds(value))
    return values


def instant_seconds(value: datetime) -> int:
    return int(value.timestamp())


def worst_shortfall(earlier_ends: list[int], later_starts: list[int], minimum_seconds: int) -> int:
    return max(0, minimum_seconds - min(later_starts) + max(earlier_ends))


def buffer_problem(
    constraints: list[ConstraintInput],
    groups: dict[str, list[FoundationInput]],
    calendar: dict,
) -> list[str]:
    """Reasons an active package buffer cannot be enforced. Empty when it can."""
    messages: list[str] = []
    for constraint in constraints:
        if not constraint.active or constraint.constraint_type != "package_buffer":
            continue
        later = package_name(constraint)
        if later not in PREVIOUS:
            messages.append(
                f"{constraint.name} is on {later}. A package buffer applies to IAC, "
                "which waits for FOU, or WTG, which waits for IAC."
            )
            continue
        mode = constraint.parameters.get("mode")
        if mode not in {"minimum", "maximize"}:
            messages.append(f"{constraint.name} must be a minimum buffer or maximize.")
            continue
        if mode == "minimum":
            try:
                days = int(constraint.parameters.get("minimum_days"))
            except (TypeError, ValueError):
                messages.append(f"{constraint.name} needs a minimum number of days.")
                continue
            if days < 0:
                messages.append(f"{constraint.name} needs a minimum number of days.")
                continue
        earlier = PREVIOUS[later]
        if not groups.get(earlier):
            messages.append(
                f"{constraint.name} needs included {earlier} activities before {later} can wait."
            )
            continue
        if not groups.get(later):
            messages.append(f"{constraint.name} needs included {later} activities.")
            continue
        if not location_links(later, groups):
            continue
        if slot_instants(calendar, earlier, len(groups[earlier]), "end") is None:
            messages.append(
                f"{constraint.name} needs a programme end date on every {earlier} sequence slot."
            )
        if slot_instants(calendar, later, len(groups[later]), "start") is None:
            messages.append(
                f"{constraint.name} needs a programme start date on every {later} sequence slot."
            )
    return messages


def apply_buffer_checks(
    evaluation: Evaluation,
    campaigns: list[CampaignResult],
    constraints: list[ConstraintInput],
    calendar: dict,
) -> None:
    """Check each package buffer from the stored orders and programme dates."""
    groups = {campaign.package: list(campaign.items) for campaign in campaigns}
    orders = {campaign.package: list(campaign.order) for campaign in campaigns}
    order_number = max((row.display_order for row in evaluation.validation_rows), default=0)
    for constraint in constraints:
        if not constraint.active or constraint.constraint_type != "package_buffer":
            continue
        order_number += 1
        row, penalty = _one_check(constraint, groups, orders, calendar, order_number)
        evaluation.validation_rows.append(row)
        evaluation.objective_penalty += penalty
        _mark(evaluation, constraint, groups, row)
    evaluation.hard_failures = sum(
        1 for row in evaluation.validation_rows if row.status == "Failed"
    )
    evaluation.soft_tradeoff_count = sum(
        1 for row in evaluation.validation_rows if row.status == "Soft trade-off"
    )
    evaluation.validation_status = "Failed" if evaluation.hard_failures else "Passed"


def _touching(cables: list[FoundationInput], location_id: str) -> list[int]:
    key = location_id.strip().casefold()
    if not key:
        return []
    return [index for index, cable in enumerate(cables) if key in endpoint_keys(cable)]


def _one_check(
    constraint: ConstraintInput,
    groups: dict[str, list[FoundationInput]],
    orders: dict[str, list[str]],
    calendar: dict,
    display_order: int,
) -> tuple[ValidationRow, int]:
    later = package_name(constraint)
    earlier = PREVIOUS.get(later, "")
    links = location_links(later, groups) if earlier else []
    gaps: list[tuple[str, int | None]] = []
    for location_id, earlier_indexes, later_indexes in links:
        gaps.append(
            (
                location_id,
                _gap_seconds(
                    groups, orders, calendar, earlier, later, earlier_indexes, later_indexes
                ),
            )
        )
    missing = [location_id for location_id, gap in gaps if gap is None]
    known = [(location_id, gap) for location_id, gap in gaps if gap is not None]
    mode = constraint.parameters.get("mode")
    if not links:
        return _row(
            constraint,
            "No paired locations",
            "Passed",
            [],
            "Locations without the previous package are left out of this buffer.",
            display_order,
        ), 0
    if missing:
        status = "Failed" if constraint.enforcement == "hard" else "Information"
        return _row(
            constraint,
            "Programme date missing",
            status,
            missing,
            "A sequenced slot has no programme date, so this buffer cannot be checked.",
            display_order,
        ), 0
    smallest = min(gap for _location_id, gap in known)
    actual = f"Smallest gap {smallest / DAY_SECONDS:.2f} days"
    if mode == "maximize":
        return _row(
            constraint,
            actual,
            "Information",
            [location_id for location_id, _gap in known],
            f"The smallest gap from {earlier} end to {later} start is reported. "
            "Maximize has no day limit.",
            display_order,
        ), 0
    minimum = int(constraint.parameters["minimum_days"]) * DAY_SECONDS
    short = [location_id for location_id, gap in known if gap < minimum]
    if constraint.enforcement == "hard":
        status = "Failed" if short else "Passed"
        explanation = (
            f"{later} starts at least {constraint.parameters['minimum_days']} days after "
            f"the {earlier} end at the same location."
        )
        if short:
            explanation = (
                f"{later} starts before the minimum buffer after {earlier}. "
                "No hard constraint was relaxed."
            )
        return _row(constraint, actual, status, short, explanation, display_order), 0
    raw = sum(max(0, minimum - gap) for _location_id, gap in known)
    ends = slot_instants(calendar, earlier, len(groups.get(earlier, [])), "end") or []
    starts = slot_instants(calendar, later, len(groups.get(later, [])), "start") or []
    limit = worst_shortfall(ends, starts, minimum) if ends and starts else 0
    max_raw = limit * len(known)
    penalty = scaled_penalty(raw, max_raw, int(constraint.severity or 0)) if max_raw else 0
    status = "Soft trade-off" if short else "Passed"
    explanation = (
        f"A shortfall under {constraint.parameters['minimum_days']} days is penalised "
        "by severity. It does not fail the run."
    )
    return _row(constraint, actual, status, short, explanation, display_order), penalty


def _gap_seconds(
    groups: dict[str, list[FoundationInput]],
    orders: dict[str, list[str]],
    calendar: dict,
    earlier: str,
    later: str,
    earlier_indexes: list[int],
    later_indexes: list[int],
) -> int | None:
    ends = [
        _placed(groups[earlier], orders.get(earlier, []), index, calendar, earlier, "end")
        for index in earlier_indexes
    ]
    starts = [
        _placed(groups[later], orders.get(later, []), index, calendar, later, "start")
        for index in later_indexes
    ]
    if any(value is None for value in ends + starts):
        return None
    return min(value for value in starts if value is not None) - max(
        value for value in ends if value is not None
    )


def _placed(
    items: list[FoundationInput],
    order: list[str],
    index: int,
    calendar: dict,
    package: str,
    edge: str,
) -> int | None:
    if index >= len(items):
        return None
    identity = items[index].foundation_id
    try:
        position = order.index(identity) + 1
    except ValueError:
        return None
    window = calendar.get(position, {}).get(package)
    if not window:
        return None
    value = window[0] if edge == "start" else window[1]
    if value is None:
        return None
    return instant_seconds(value)


def _row(
    constraint: ConstraintInput,
    actual: str,
    status: str,
    affected: list[str],
    explanation: str,
    display_order: int,
) -> ValidationRow:
    later = package_name(constraint)
    if constraint.parameters.get("mode") == "maximize":
        target = "Maximize the smallest gap"
    else:
        target = f"Minimum {constraint.parameters.get('minimum_days')} days"
    return ValidationRow(
        check_name=f"{later}: Package buffer",
        constraint_name=constraint.name,
        target=target,
        actual_result=actual,
        status=status,
        affected_foundations=", ".join(affected),
        explanation=explanation,
        display_order=display_order,
    )


def _mark(
    evaluation: Evaluation,
    constraint: ConstraintInput,
    groups: dict[str, list[FoundationInput]],
    row: ValidationRow,
) -> None:
    if row.status not in {"Failed", "Soft trade-off"}:
        return
    later = package_name(constraint)
    if later not in PREVIOUS or not row.affected_foundations:
        return
    names = {
        part.strip().casefold()
        for part in row.affected_foundations.split(",")
        if part.strip()
    }
    cables = groups.get("IAC", [])
    cable_ids = {
        cable.foundation_id
        for cable in cables
        if endpoint_keys(cable) & names
    }
    earlier = PREVIOUS[later]
    for sequence in evaluation.sequence_rows:
        identity = sequence.foundation_id.casefold()
        if sequence.foundation_id in cable_ids or (
            identity in names and sequence.package in {earlier, later}
        ):
            current = sequence.governing_constraints
            if constraint.name not in current.split("; "):
                sequence.governing_constraints = "; ".join(
                    part for part in (current, constraint.name) if part
                )
