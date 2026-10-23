"""Direct conflict checks that run before CP-SAT is started."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.constraints.services.matching import (
    ORDERING_ATTRIBUTES,
    column_state,
    matching_foundations,
)
from apps.constraints.services.parameters import validate_parameters
from apps.optimisation.services.geometry import (
    required_trips,
    sequence_positions_for_trip,
    trip_number,
    trip_slot_count,
    vessel_position,
)
from apps.optimisation.services.scaling import MAX_DISTANCE_FOUNDATIONS, MAX_INCLUDED_FOUNDATIONS
from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig


@dataclass
class _Bounds:
    fixed_trips: set[int] = field(default_factory=set)
    fixed_positions: set[int] = field(default_factory=set)
    fixed_slots: set[tuple[int, int]] = field(default_factory=set)
    earliest: int | None = None
    latest: int | None = None
    allowed: set[int] | None = None
    excluded: set[int] = field(default_factory=set)


def find_conflicts(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    columns_present: set[str],
) -> list[str]:
    included = [item for item in foundations if item.include]
    active = [item for item in constraints if item.active]
    conflicts: list[str] = []
    count = len(included)
    capacity = vessel.max_foundations_per_trip

    if count == 0:
        conflicts.append("No included foundations are available to sequence.")
    if capacity < 1:
        conflicts.append("Maximum foundations per trip must be a positive integer.")
        return _unique(conflicts)
    if count > MAX_INCLUDED_FOUNDATIONS:
        conflicts.append(
            f"This scenario has {count} included foundations. "
            f"MVP 1 solves up to {MAX_INCLUDED_FOUNDATIONS} included foundations at a time."
        )
    if count and not vessel.allow_partial_final_trip and count % capacity != 0:
        conflicts.append(
            f"Insufficient trip slots: {count} included foundations with a capacity of {capacity} "
            "and the partial final trip disabled."
        )

    state = column_state(foundations, columns_present)
    for foundation in included:
        if foundation.fixed_position is not None and foundation.fixed_position > capacity:
            conflicts.append(
                f"Foundation {foundation.foundation_id} has Fixed_Position "
                f"{foundation.fixed_position}, which is above the vessel capacity of {capacity}."
            )
        if (
            foundation.earliest_sequence is not None
            and foundation.latest_sequence is not None
            and foundation.earliest_sequence > foundation.latest_sequence
        ):
            conflicts.append(
                f"Foundation {foundation.foundation_id} has Earliest_Sequence greater than Latest_Sequence."
            )

    bounds: dict[str, _Bounds] = {item.foundation_id: _Bounds() for item in included}
    hard_payloads: list[tuple[str, Decimal]] = []
    groups: dict[str, str] = {}
    separate_pairs: list[tuple[str, str, str]] = []
    rule_limits: dict[tuple[Any, ...], dict[str, int]] = defaultdict(dict)

    for constraint in active:
        parameter_errors = validate_parameters(
            constraint.constraint_type,
            constraint.parameters,
            foundations=foundations,
            vessel=vessel,
            columns_present=columns_present,
        )
        if parameter_errors:
            conflicts.append(f"{constraint.name}: " + " ".join(parameter_errors))
            continue
        column_conflict = _missing_column(constraint, state)
        if column_conflict:
            conflicts.append(column_conflict)
            continue
        if (
            constraint.constraint_type == "minimise_within_trip_distance"
            and count > MAX_DISTANCE_FOUNDATIONS
        ):
            conflicts.append(
                f"{constraint.name} minimises within-trip distance in the solver. "
                f"MVP 1 does this for up to {MAX_DISTANCE_FOUNDATIONS} included foundations."
            )
            continue
        if constraint.enforcement != "hard":
            continue
        _apply_hard(
            constraint,
            included,
            vessel,
            bounds,
            hard_payloads,
            groups,
            separate_pairs,
            rule_limits,
            conflicts,
        )

    _evaluate_bounds(
        included, vessel, bounds, hard_payloads, groups, separate_pairs, rule_limits, conflicts
    )
    conflicts.extend(find_precedence_cycles(active))
    return _unique(conflicts)


def _missing_column(constraint: ConstraintInput, state: dict[str, dict[str, bool]]) -> str:
    attribute = constraint.parameters.get("attribute")
    if constraint.constraint_type == "minimise_within_trip_distance" and not (
        state["Easting_m"]["complete"] and state["Northing_m"]["complete"]
    ):
        return (
            f"{constraint.name} cannot run because distance constraints require Easting_m and "
            "Northing_m on every included foundation."
        )
    if constraint.constraint_type == "difficulty_progression":
        attribute = constraint.parameters.get("attribute") or "Difficulty_Value"
        if attribute not in state or not state[attribute]["complete"]:
            return (
                f"{constraint.name} cannot run because difficulty progression requires "
                f"{attribute} on every included foundation."
            )
    if (
        constraint.constraint_type == "delivery_sequence_alignment"
        and not state["Delivery_Sequence"]["complete"]
    ):
        return (
            f"{constraint.name} cannot run because delivery-sequence alignment requires "
            "Delivery_Sequence on every included foundation."
        )
    if constraint.constraint_type == "attribute_ordering":
        if (
            not attribute
            or attribute not in ORDERING_ATTRIBUTES
            or not state[attribute]["complete"]
        ):
            return (
                f"{constraint.name} cannot run because attribute ordering requires a complete "
                f"{attribute or 'numeric'} column."
            )
    if attribute == "Punch_Through" and (
        not state["Punch_Through"]["present"] or not state["Punch_Through"]["any"]
    ):
        return f"{constraint.name} cannot run because punch-through rules require Punch_Through values."
    if attribute and attribute in state and not state[attribute]["present"]:
        return (
            f"{constraint.name} depends on {attribute}, which is missing from the uploaded dataset."
        )
    return ""


def _apply_hard(
    constraint: ConstraintInput,
    included: list[FoundationInput],
    vessel: VesselConfig,
    bounds: dict[str, _Bounds],
    hard_payloads: list[tuple[str, Decimal]],
    groups: dict[str, str],
    separate_pairs: list[tuple[str, str, str]],
    rule_limits: dict[tuple[Any, ...], dict[str, int]],
    conflicts: list[str],
) -> None:
    parameters = constraint.parameters
    kind = constraint.constraint_type
    capacity = vessel.max_foundations_per_trip
    count = len(included)
    trips = required_trips(count, capacity)

    if kind == "maximum_trip_payload":
        hard_payloads.append((constraint.name, Decimal(str(parameters["maximum_payload_t"]))))
        return
    if kind == "fixed_trip":
        foundation_id = str(parameters["foundation_id"])
        trip = int(parameters["trip_number"])
        if foundation_id not in bounds:
            conflicts.append(
                f"{constraint.name} references foundation {foundation_id}, which does not exist."
            )
            return
        if trips and trip > trips:
            conflicts.append(
                f"{constraint.name} fixes {foundation_id} to trip {trip}, but this dataset only needs {trips} trips."
            )
        bounds[foundation_id].fixed_trips.add(trip)
        return
    if kind == "fixed_vessel_position":
        foundation_id = str(parameters["foundation_id"])
        position = int(parameters["position_number"])
        if foundation_id not in bounds:
            conflicts.append(
                f"{constraint.name} references foundation {foundation_id}, which does not exist."
            )
            return
        if position > capacity:
            conflicts.append(
                f"{constraint.name} fixes {foundation_id} to vessel position {position}, "
                f"which is above the capacity of {capacity}."
            )
        trip_number_value = parameters.get("trip_number")
        if trip_number_value not in (None, ""):
            trip = int(trip_number_value)
            if trips and trip > trips:
                conflicts.append(
                    f"{constraint.name} fixes {foundation_id} to trip {trip}, which does not exist for this dataset."
                )
            bounds[foundation_id].fixed_slots.add((trip, position))
            bounds[foundation_id].fixed_trips.add(trip)
        bounds[foundation_id].fixed_positions.add(position)
        return
    if kind in {"allowed_positions", "excluded_positions"}:
        positions = {
            int(value)
            for value in parameters[
                "allowed_positions" if kind == "allowed_positions" else "excluded_positions"
            ]
        }
        matched = matching_foundations(included, parameters)
        if not matched and parameters.get("foundation_id"):
            conflicts.append(f"{constraint.name} references a foundation that does not exist.")
        for foundation in matched:
            record = bounds[foundation.foundation_id]
            if kind == "allowed_positions":
                record.allowed = positions if record.allowed is None else record.allowed & positions
            else:
                record.excluded |= positions
        return
    if kind in {"earliest_sequence", "latest_sequence"}:
        sequence = _resolved_sequence(parameters, kind, capacity)
        matched = _sequence_targets(included, parameters)
        if parameters.get("foundation_id") and not matched:
            conflicts.append(
                f"{constraint.name} references foundation {parameters.get('foundation_id')}, which does not exist."
            )
        for foundation in matched:
            record = bounds[foundation.foundation_id]
            if kind == "earliest_sequence":
                record.earliest = (
                    sequence if record.earliest is None else max(record.earliest, sequence)
                )
            else:
                record.latest = sequence if record.latest is None else min(record.latest, sequence)
        return
    if kind == "precedence":
        predecessor = str(parameters["predecessor_foundation_id"])
        successor = str(parameters["successor_foundation_id"])
        for foundation_id in (predecessor, successor):
            if foundation_id not in bounds:
                conflicts.append(
                    f"{constraint.name} references foundation {foundation_id}, which does not exist."
                )
        return
    if kind == "maximum_matching_per_trip":
        maximum = int(parameters["maximum_count"])
        if maximum > capacity:
            return
        signature = _rule_signature(parameters)
        rule_limits[signature]["max"] = min(rule_limits[signature].get("max", maximum), maximum)
        if maximum > capacity:
            conflicts.append(f"{constraint.name} allows more matches than the trip capacity.")
        return
    if kind == "minimum_matching_per_trip":
        minimum = int(parameters["minimum_count"])
        applicable = _applicable_trips(parameters, trips)
        if minimum > capacity:
            conflicts.append(
                f"{constraint.name} requires {minimum} matching foundations, above the trip capacity of {capacity}."
            )
        for trip in applicable:
            slots = trip_slot_count(trip, count, capacity)
            if slots and minimum > slots:
                conflicts.append(
                    f"{constraint.name} requires {minimum} matching foundations on trip {trip}, "
                    f"which only has {slots} slots."
                )
        matched = matching_foundations(included, parameters)
        if applicable and len(matched) < minimum * len(applicable):
            conflicts.append(
                f"{constraint.name} needs {minimum} matching foundations on {len(applicable)} trips, "
                f"but only {len(matched)} included foundations match."
            )
        signature = _rule_signature(parameters)
        rule_limits[signature]["min"] = max(rule_limits[signature].get("min", minimum), minimum)
        return
    if kind == "same_trip":
        identifiers = [str(item) for item in parameters["foundation_ids"]]
        for foundation_id in identifiers:
            if foundation_id not in bounds:
                conflicts.append(
                    f"{constraint.name} references foundation {foundation_id}, which does not exist."
                )
        if len(identifiers) > capacity:
            conflicts.append(
                f"{constraint.name} groups {len(identifiers)} foundations, above the trip capacity of {capacity}."
            )
        root = _find(groups, identifiers[0])
        for foundation_id in identifiers[1:]:
            groups[_find(groups, foundation_id)] = root
        return
    if kind == "separate_trip":
        identifiers = [str(item) for item in parameters["foundation_ids"]]
        for foundation_id in identifiers:
            if foundation_id not in bounds:
                conflicts.append(
                    f"{constraint.name} references foundation {foundation_id}, which does not exist."
                )
        for index, left in enumerate(identifiers):
            for right in identifiers[index + 1 :]:
                separate_pairs.append((left, right, constraint.name))
        return


def _evaluate_bounds(
    included: list[FoundationInput],
    vessel: VesselConfig,
    bounds: dict[str, _Bounds],
    hard_payloads: list[tuple[str, Decimal]],
    groups: dict[str, str],
    separate_pairs: list[tuple[str, str, str]],
    rule_limits: dict[tuple[Any, ...], dict[str, int]],
    conflicts: list[str],
) -> None:
    capacity = vessel.max_foundations_per_trip
    count = len(included)
    forced: dict[int, list[FoundationInput]] = defaultdict(list)
    by_id = {item.foundation_id: item for item in included}

    for foundation in included:
        record = bounds[foundation.foundation_id]
        if len(record.fixed_trips) > 1:
            joined = ", ".join(str(trip) for trip in sorted(record.fixed_trips))
            conflicts.append(
                f"Foundation {foundation.foundation_id} is fixed to more than one trip ({joined})."
            )
        if len(record.fixed_positions) > 1:
            joined = ", ".join(str(position) for position in sorted(record.fixed_positions))
            conflicts.append(
                f"Foundation {foundation.foundation_id} is fixed to more than one vessel position ({joined})."
            )
        if len(record.fixed_slots) > 1:
            conflicts.append(
                f"Foundation {foundation.foundation_id} is fixed to more than one trip and position."
            )
        if (
            record.earliest is not None
            and record.latest is not None
            and record.earliest > record.latest
        ):
            conflicts.append(
                f"Foundation {foundation.foundation_id} has a hard earliest sequence {record.earliest} "
                f"after its hard latest sequence {record.latest}."
            )
        if record.earliest is not None and count and record.earliest > count:
            conflicts.append(
                f"Foundation {foundation.foundation_id} has earliest sequence {record.earliest}, "
                f"beyond the {count} included foundations."
            )
        if record.allowed is not None and not record.allowed:
            conflicts.append(
                f"Foundation {foundation.foundation_id} has contradictory hard allowed-position rules."
            )
        if (
            record.allowed is not None
            and record.fixed_positions
            and not record.fixed_positions <= record.allowed
        ):
            conflicts.append(
                f"Foundation {foundation.foundation_id} is fixed to a position outside its allowed positions."
            )
        if record.fixed_positions & record.excluded:
            conflicts.append(
                f"Foundation {foundation.foundation_id} is fixed to a position that is also excluded."
            )
        reachable = _reachable(record, count, capacity)
        if reachable is not None and not reachable:
            conflicts.append(
                f"Foundation {foundation.foundation_id} has no vessel position left after its hard "
                "trip, position, and sequence rules."
            )
        possible_trips = _possible_trips(record, count, capacity)
        if len(record.fixed_trips) == 1:
            only_trip = next(iter(record.fixed_trips))
            if possible_trips and only_trip not in possible_trips:
                conflicts.append(
                    f"Foundation {foundation.foundation_id} is fixed to trip {only_trip}, which is outside "
                    "its allowed sequence window."
                )
        if len(possible_trips) == 1:
            forced[next(iter(possible_trips))].append(foundation)

    for trip, group in forced.items():
        slots = trip_slot_count(trip, count, capacity)
        if len(group) > slots:
            names = ", ".join(item.foundation_id for item in group)
            conflicts.append(
                f"Trip {trip} has {len(group)} foundations fixed to it ({names}), above its {slots} slots."
            )

    if hard_payloads:
        limit = min(payload for _, payload in hard_payloads)
        limit_name = min(hard_payloads, key=lambda item: item[1])[0]
        for foundation in included:
            if foundation.weight_t is not None and foundation.weight_t > limit:
                conflicts.append(
                    f"Foundation {foundation.foundation_id} weighs {foundation.weight_t} t, above the hard "
                    f"payload limit of {limit} t from {limit_name}."
                )
        for trip, group in forced.items():
            total = sum((item.weight_t or Decimal("0")) for item in group)
            if total > limit:
                names = ", ".join(item.foundation_id for item in group)
                conflicts.append(
                    f"Foundations fixed to trip {trip} ({names}) weigh {total} t, above the hard payload "
                    f"limit of {limit} t."
                )

    for left, right, name in separate_pairs:
        if left in by_id and right in by_id and _find(groups, left) == _find(groups, right):
            conflicts.append(
                f"{name} separates {left} and {right}, but a hard same-trip rule groups them."
            )

    for signature, limits in rule_limits.items():
        if "min" in limits and "max" in limits and limits["min"] > limits["max"]:
            conflicts.append(
                "Hard minimum and maximum counts contradict each other for the same attribute rule "
                f"({signature[0]} {signature[1]} {signature[2]})."
            )


def find_precedence_cycles(constraints: list[ConstraintInput]) -> list[str]:
    """Report direct two-foundation hard precedence cycles."""
    edges: dict[tuple[str, str], str] = {}
    for constraint in constraints:
        if (
            not constraint.active
            or constraint.enforcement != "hard"
            or constraint.constraint_type != "precedence"
        ):
            continue
        predecessor = str(constraint.parameters.get("predecessor_foundation_id", ""))
        successor = str(constraint.parameters.get("successor_foundation_id", ""))
        edges[(predecessor, successor)] = constraint.name
    messages: list[str] = []
    seen: set[tuple[str, str]] = set()
    for predecessor, successor in list(edges):
        if (successor, predecessor) in edges and (predecessor, successor) not in seen:
            seen.add((predecessor, successor))
            seen.add((successor, predecessor))
            messages.append(
                f"Hard precedence rules contradict each other for {predecessor} and {successor}."
            )
    return messages


def _resolved_sequence(parameters: dict[str, Any], kind: str, capacity: int) -> int:
    sequence_key = "earliest_sequence" if kind == "earliest_sequence" else "latest_sequence"
    trip_key = "earliest_trip" if kind == "earliest_sequence" else "latest_trip"
    if parameters.get(sequence_key) not in (None, ""):
        return int(parameters[sequence_key])
    trip = int(parameters[trip_key])
    if kind == "earliest_sequence":
        return (trip - 1) * capacity + 1
    return trip * capacity


def _sequence_targets(
    included: list[FoundationInput], parameters: dict[str, Any]
) -> list[FoundationInput]:
    if parameters.get("attribute"):
        return matching_foundations(included, parameters)
    if parameters.get("foundation_id"):
        wanted = str(parameters["foundation_id"])
        return [item for item in included if item.foundation_id == wanted]
    return []


def _applicable_trips(parameters: dict[str, Any], trips: int) -> list[int]:
    raw = parameters.get("applicable_trips")
    if not raw:
        return list(range(1, trips + 1))
    return [int(trip) for trip in raw if 1 <= int(trip) <= max(trips, 0) or trips == 0]


def _rule_signature(parameters: dict[str, Any]) -> tuple[Any, ...]:
    return (
        parameters.get("attribute"),
        parameters.get("operator"),
        str(parameters.get("value")),
        str(parameters.get("value_to")),
    )


def _find(groups: dict[str, str], foundation_id: str) -> str:
    groups.setdefault(foundation_id, foundation_id)
    if groups[foundation_id] != foundation_id:
        groups[foundation_id] = _find(groups, groups[foundation_id])
    return groups[foundation_id]


def _reachable(record: _Bounds, count: int, capacity: int) -> set[int] | None:
    if count <= 0:
        return set()
    sequences = range(1, count + 1)
    if record.earliest is not None or record.latest is not None:
        start = record.earliest or 1
        end = record.latest or count
        sequences = range(max(1, start), min(count, end) + 1)
    if len(record.fixed_trips) == 1:
        trip = next(iter(record.fixed_trips))
        trip_sequences = set(sequence_positions_for_trip(trip, count, capacity))
        sequences = [sequence for sequence in sequences if sequence in trip_sequences]
    positions = {vessel_position(sequence, capacity) for sequence in sequences}
    if record.allowed is not None:
        positions &= record.allowed
    positions -= record.excluded
    if record.fixed_positions:
        positions &= record.fixed_positions
    return positions


def _possible_trips(record: _Bounds, count: int, capacity: int) -> set[int]:
    if count <= 0:
        return set()
    start = record.earliest or 1
    end = record.latest or count
    sequences = range(max(1, start), min(count, end) + 1)
    trips = {trip_number(sequence, capacity) for sequence in sequences}
    if record.fixed_trips:
        trips &= record.fixed_trips
    return trips


def _unique(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for message in messages:
        if message and message not in seen:
            seen.add(message)
            ordered.append(message)
    return ordered
