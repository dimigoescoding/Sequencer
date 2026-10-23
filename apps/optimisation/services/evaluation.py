"""Independent checks of a finished sequence.

Trip and vessel position are derived here from the installation sequence.
Nothing in this module reads solver assertions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.constraints.services.matching import matching_foundations
from apps.optimisation.services.geometry import (
    positions_in_trip_window,
    required_trips,
    sequence_positions_for_trip,
    trip_number,
    trip_slot_count,
    vessel_position,
)
from apps.optimisation.services.metrics import (
    attribute_span,
    attribute_values,
    count_inversions,
    delivery_excess,
    delivery_max_raw,
    ordering_pairs,
    window_pair_count,
    window_violation,
)
from apps.optimisation.services.routing import format_nautical_miles, metres_between
from apps.optimisation.services.scaling import scaled_penalty, weight_kg
from apps.optimisation.services.solver import _bound_targets, _sequence_bound_value
from apps.optimisation.services.types import (
    ConstraintInput,
    Evaluation,
    FoundationInput,
    SequenceRow,
    TripRow,
    ValidationRow,
    VesselConfig,
)


@dataclass
class _Placement:
    foundation: FoundationInput
    sequence: int
    trip: int
    position: int


def evaluate(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    order: list[str],
) -> Evaluation:
    included = [item for item in foundations if item.include]
    excluded = [item for item in foundations if not item.include]
    active = sorted(
        [item for item in constraints if item.active],
        key=lambda item: (item.display_order, item.constraint_id or 0),
    )
    capacity = vessel.max_foundations_per_trip
    by_id = {item.foundation_id: item for item in foundations}
    placements = _placements(order, by_id, capacity)
    checks: list[ValidationRow] = []
    order_number = 0

    def add(
        check_name: str,
        constraint_name: str,
        target: str,
        actual: str,
        status: str,
        affected: list[str],
        explanation: str,
    ) -> None:
        nonlocal order_number
        order_number += 1
        checks.append(
            ValidationRow(
                check_name=check_name,
                constraint_name=constraint_name,
                target=target,
                actual_result=actual,
                status=status,
                affected_foundations=", ".join(affected),
                explanation=explanation,
                display_order=order_number,
            )
        )

    included_ids = [item.foundation_id for item in included]
    result_ids = [
        item.foundation.foundation_id for item in placements if item.foundation.foundation_id
    ]
    unknown = [item for item in order if item not in by_id]
    duplicates = sorted({item for item in result_ids if result_ids.count(item) > 1})
    missing = [item for item in included_ids if result_ids.count(item) != 1]
    excluded_present = [item.foundation_id for item in excluded if item.foundation_id in result_ids]

    add(
        "Included foundation count",
        "",
        str(len(included_ids)),
        str(len(result_ids)),
        "Passed" if len(result_ids) == len(included_ids) else "Failed",
        missing,
        "The result must contain the same number of rows as included foundations.",
    )
    add(
        "Unique Foundation_ID",
        "",
        "No duplicate Foundation_ID",
        "Duplicates: " + ", ".join(duplicates)
        if duplicates
        else "All Foundation_ID values are unique",
        "Failed" if duplicates or unknown else "Passed",
        duplicates or unknown,
        "Each result row must use a different Foundation_ID.",
    )
    add(
        "Included foundations present",
        "",
        ", ".join(included_ids),
        ", ".join(result_ids),
        "Passed" if not missing and not duplicates else "Failed",
        missing,
        "Every included foundation appears exactly once.",
    )
    add(
        "Excluded foundations absent",
        "",
        "No excluded foundation",
        "Present: " + ", ".join(excluded_present)
        if excluded_present
        else "No excluded foundations",
        "Failed" if excluded_present else "Passed",
        excluded_present,
        "Foundations with Include set to No must not enter the sequence.",
    )
    structural_ok = not missing and not duplicates and not unknown and not excluded_present
    _add_trip_structure(
        add, placements, len(included), capacity, vessel.allow_partial_final_trip, structural_ok
    )
    add(
        "Trip derivation",
        "",
        f"Capacity {capacity}",
        "Derived from installation sequence",
        "Information",
        [],
        "Trip is floor((sequence-1)/N)+1 and vessel position is ((sequence-1) mod N)+1.",
    )

    failed_ids: set[str] = set(missing) | set(duplicates) | set(excluded_present)
    penalties: dict[str, int] = defaultdict(int)
    governing: dict[str, list[str]] = defaultdict(list)
    objective_penalty = 0
    trip_payload_failed: set[int] = set()
    trip_payload_soft: set[int] = set()
    trip_position_failed: set[int] = set()

    if structural_ok:
        for constraint in active:
            penalty, failed, position_trips, payload_trips, soft_trips = _check_constraint(
                constraint,
                included,
                placements,
                vessel,
                add,
                governing,
                penalties,
            )
            objective_penalty += penalty
            failed_ids.update(failed)
            trip_position_failed.update(position_trips)
            trip_payload_failed.update(payload_trips)
            trip_payload_soft.update(soft_trips)

    sequence_rows = _sequence_rows(placements, penalties, governing, failed_ids, structural_ok)
    trip_rows = _trip_rows(
        placements,
        active,
        vessel,
        trip_payload_failed,
        trip_payload_soft,
        trip_position_failed,
        structural_ok,
    )
    hard_failures = sum(1 for row in checks if row.status == "Failed")
    tradeoffs = sum(1 for row in checks if row.status == "Soft trade-off")
    return Evaluation(
        sequence_rows=sequence_rows,
        trip_rows=trip_rows,
        validation_rows=checks,
        validation_status="Passed" if hard_failures == 0 else "Failed",
        soft_tradeoff_count=tradeoffs,
        hard_failures=hard_failures,
        objective_penalty=objective_penalty,
    )


def _placements(
    order: list[str], by_id: dict[str, FoundationInput], capacity: int
) -> list[_Placement]:
    placements: list[_Placement] = []
    for sequence, foundation_id in enumerate(order, start=1):
        foundation = by_id.get(foundation_id)
        if foundation is None:
            continue
        placements.append(
            _Placement(
                foundation=foundation,
                sequence=sequence,
                trip=trip_number(sequence, capacity),
                position=vessel_position(sequence, capacity),
            )
        )
    return placements


def _add_trip_structure(
    add, placements, count, capacity, allow_partial: bool, structural_ok: bool
) -> None:
    if not structural_ok or count == 0:
        add(
            "Trip capacity",
            "",
            f"Trips filled to {capacity} except a permitted final trip",
            "Not evaluated because the sequence is not a complete permutation",
            "Failed",
            [],
            "Trip capacity is checked only after the foundation set is valid.",
        )
        add(
            "Partial final trip",
            "",
            "Enabled" if allow_partial else "Disabled",
            "Not evaluated",
            "Failed" if not allow_partial else "Information",
            [],
            "The partial-final-trip rule is checked with trip capacity.",
        )
        return
    trips = required_trips(count, capacity)
    counts: dict[int, int] = defaultdict(int)
    for placement in placements:
        counts[placement.trip] += 1
    capacity_failed = False
    partial_failed = False
    for trip in range(1, trips + 1):
        expected = trip_slot_count(trip, count, capacity)
        actual = counts.get(trip, 0)
        if trip < trips and actual != capacity:
            capacity_failed = True
        if trip == trips and actual != expected:
            capacity_failed = True
        if trip == trips and not allow_partial and actual != capacity:
            partial_failed = True
    add(
        "Trip capacity",
        "",
        f"{capacity} foundations on every trip except the final trip",
        "; ".join(f"trip {trip}={counts.get(trip, 0)}" for trip in range(1, trips + 1)),
        "Failed" if capacity_failed else "Passed",
        [],
        "Earlier trips must be full. The final trip contains the remaining foundations.",
    )
    add(
        "Partial final trip",
        "",
        "Allowed" if allow_partial else "Not allowed",
        f"Final trip count {counts.get(trips, 0)}",
        "Failed" if partial_failed else "Passed",
        [],
        "A short final trip is accepted only when the scenario allows it.",
    )


def _check_constraint(
    constraint: ConstraintInput,
    included: list[FoundationInput],
    placements: list[_Placement],
    vessel: VesselConfig,
    add,
    governing: dict[str, list[str]],
    penalties: dict[str, int],
) -> tuple[int, set[str], set[int], set[int], set[int]]:
    kind = constraint.constraint_type
    if kind == "maximum_trip_payload":
        return _payload(constraint, placements, add, governing)
    if kind == "fixed_trip":
        return _fixed_trip(constraint, placements, add, governing, penalties)
    if kind == "fixed_vessel_position":
        return _fixed_position(constraint, placements, vessel, add, governing, penalties)
    if kind == "allowed_positions":
        return _positions(
            constraint, placements, allowed=True, add=add, governing=governing, penalties=penalties
        )
    if kind == "excluded_positions":
        return _positions(
            constraint, placements, allowed=False, add=add, governing=governing, penalties=penalties
        )
    if kind in {"earliest_sequence", "latest_sequence"}:
        return _window(constraint, included, placements, vessel, add, governing, penalties)
    if kind == "precedence":
        return _precedence(constraint, placements, add, governing, penalties)
    if kind == "maximum_matching_per_trip":
        return _count_limit(
            constraint,
            placements,
            vessel,
            minimum=False,
            add=add,
            governing=governing,
            penalties=penalties,
        )
    if kind == "minimum_matching_per_trip":
        return _count_limit(
            constraint,
            placements,
            vessel,
            minimum=True,
            add=add,
            governing=governing,
            penalties=penalties,
        )
    if kind == "same_trip":
        return _grouping(
            constraint,
            placements,
            separate=False,
            add=add,
            governing=governing,
            penalties=penalties,
        )
    if kind == "separate_trip":
        return _grouping(
            constraint, placements, separate=True, add=add, governing=governing, penalties=penalties
        )
    if kind == "attribute_ordering":
        return _ordering(constraint, included, placements, vessel, add, governing, penalties)
    if kind == "delivery_sequence_alignment":
        return _delivery(constraint, included, placements, add, governing, penalties)
    if kind == "difficulty_progression":
        return _difficulty(constraint, included, placements, vessel, add, governing, penalties)
    if kind == "minimise_within_trip_distance":
        return _distance(constraint, placements, vessel, add, governing)
    if kind == "matching_installed_first":
        return _installed_first(constraint, placements, add, governing, penalties)
    if kind == "avoid_matching_in_first_trips":
        return _avoid_first_trips(constraint, placements, vessel, add, governing, penalties)
    add(
        constraint.constraint_type,
        constraint.name,
        "",
        "Not evaluated",
        "Failed" if constraint.enforcement == "hard" else "Information",
        [],
        "This constraint type was not recognised by the independent validator.",
    )
    return 0, set(), set(), set(), set()


def _mark(governing: dict[str, list[str]], foundation_ids: list[str], name: str) -> None:
    for foundation_id in foundation_ids:
        if name not in governing[foundation_id]:
            governing[foundation_id].append(name)


def _empty() -> tuple[int, set[str], set[int], set[int], set[int]]:
    return 0, set(), set(), set(), set()


def _payload(
    constraint, placements, add, governing
) -> tuple[int, set[str], set[int], set[int], set[int]]:
    limit = Decimal(str(constraint.parameters["maximum_payload_t"]))
    grouped: dict[int, list[_Placement]] = defaultdict(list)
    for placement in placements:
        grouped[placement.trip].append(placement)
    raw_grams = 0
    bad_trips: list[int] = []
    affected: list[str] = []
    limit_kg = weight_kg(limit)
    for trip, group in sorted(grouped.items()):
        total_kg = sum(weight_kg(item.foundation.weight_t or Decimal("0")) for item in group)
        if total_kg > limit_kg:
            bad_trips.append(trip)
            affected.extend(item.foundation.foundation_id for item in group)
            raw_grams += total_kg - limit_kg
    _mark(governing, [item.foundation.foundation_id for item in placements], constraint.name)
    max_raw = max(
        sum(weight_kg(item.foundation.weight_t or Decimal("0")) for item in placements), 1
    )
    if constraint.enforcement == "hard":
        add(
            "Hard payload limit",
            constraint.name,
            f"<= {limit} t",
            "Exceeded on trips " + ", ".join(map(str, bad_trips)) if bad_trips else "Within limit",
            "Failed" if bad_trips else "Passed",
            affected,
            "The independent check sums Weight_t on each derived trip.",
        )
        return 0, set(affected), set(), set(bad_trips), set()
    penalty = scaled_penalty(raw_grams, max_raw, constraint.severity or 0)
    add(
        "Soft payload limit",
        constraint.name,
        f"<= {limit} t",
        f"penalty={penalty}; excess_kg={raw_grams}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "A soft payload limit permits overload. The excess is a trade-off, not a hard failure. "
        "An overloaded result is allowed only because this constraint was saved as soft.",
    )
    return penalty, set(), set(), set(), set(bad_trips)


def _fixed_trip(constraint, placements, add, governing, penalties):
    foundation_id = str(constraint.parameters["foundation_id"])
    trip = int(constraint.parameters["trip_number"])
    _mark(governing, [foundation_id], constraint.name)
    actual = next(
        (item.trip for item in placements if item.foundation.foundation_id == foundation_id), None
    )
    ok = actual == trip
    if constraint.enforcement == "hard":
        add(
            "Fixed trip",
            constraint.name,
            f"{foundation_id} on trip {trip}",
            f"Trip {actual}",
            "Passed" if ok else "Failed",
            [] if ok else [foundation_id],
            "The foundation must be on the selected trip.",
        )
        return (0, set() if ok else {foundation_id}, set() if ok else {actual or 0}, set(), set())
    penalty = 0 if ok else scaled_penalty(1, 1, constraint.severity or 0)
    penalties[foundation_id] += penalty
    add(
        "Soft fixed trip",
        constraint.name,
        f"{foundation_id} on trip {trip}",
        f"Trip {actual}; penalty={penalty}",
        "Passed" if ok else "Soft trade-off",
        [] if ok else [foundation_id],
        "The foundation is preferred on this trip.",
    )
    return penalty, set(), set(), set(), set()


def _fixed_position(constraint, placements, vessel, add, governing, penalties):
    foundation_id = str(constraint.parameters["foundation_id"])
    position = int(constraint.parameters["position_number"])
    trip_number_value = constraint.parameters.get("trip_number")
    _mark(governing, [foundation_id], constraint.name)
    placement = next(
        (item for item in placements if item.foundation.foundation_id == foundation_id), None
    )
    ok = False
    actual = "missing"
    if placement is not None:
        actual = f"trip {placement.trip} position {placement.position}"
        ok = placement.position == position
        if trip_number_value not in (None, ""):
            ok = ok and placement.trip == int(trip_number_value)
    target = f"position {position}"
    if trip_number_value not in (None, ""):
        target = f"trip {trip_number_value} {target}"
    if constraint.enforcement == "hard":
        add(
            "Fixed vessel position",
            constraint.name,
            f"{foundation_id} at {target}",
            actual,
            "Passed" if ok else "Failed",
            [] if ok else [foundation_id],
            "Vessel position is derived from the installation sequence.",
        )
        bad_trips = set() if ok or placement is None else {placement.trip}
        return 0, set() if ok else {foundation_id}, bad_trips, set(), set()
    penalty = 0 if ok else scaled_penalty(1, 1, constraint.severity or 0)
    penalties[foundation_id] += penalty
    add(
        "Soft fixed vessel position",
        constraint.name,
        f"{foundation_id} at {target}",
        f"{actual}; penalty={penalty}",
        "Passed" if ok else "Soft trade-off",
        [] if ok else [foundation_id],
        "The vessel position is preferred.",
    )
    return penalty, set(), set(), set(), set()


def _positions(constraint, placements, *, allowed: bool, add, governing, penalties):
    key = "allowed_positions" if allowed else "excluded_positions"
    selected = {int(item) for item in constraint.parameters[key]}
    matched = {
        item.foundation_id
        for item in matching_foundations(
            [item.foundation for item in placements], constraint.parameters
        )
    }
    _mark(governing, sorted(matched), constraint.name)
    bad = []
    for placement in placements:
        if placement.foundation.foundation_id not in matched:
            continue
        in_set = placement.position in selected
        if allowed and not in_set:
            bad.append(placement.foundation.foundation_id)
        if not allowed and in_set:
            bad.append(placement.foundation.foundation_id)
    label = "Allowed positions" if allowed else "Excluded positions"
    if constraint.enforcement == "hard":
        add(
            label,
            constraint.name,
            ", ".join(map(str, sorted(selected))),
            "Violations: " + ", ".join(bad) if bad else "Respected",
            "Failed" if bad else "Passed",
            bad,
            "The attribute rule was applied to the uploaded foundation values.",
        )
        bad_trips = {item.trip for item in placements if item.foundation.foundation_id in bad}
        return 0, set(bad), bad_trips, set(), set()
    penalty = scaled_penalty(len(bad), max(len(matched), 1), constraint.severity or 0) if bad else 0
    share = scaled_penalty(1, max(len(matched), 1), constraint.severity or 0) if bad else 0
    for foundation_id in bad:
        penalties[foundation_id] += share
    add(
        f"Soft {label.lower()}",
        constraint.name,
        ", ".join(map(str, sorted(selected))),
        f"violations={len(bad)}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        bad,
        "Positions outside the preference contribute a soft penalty.",
    )
    return penalty, set(), set(), set(), set()


def _window(constraint, included, placements, vessel, add, governing, penalties):
    earliest = constraint.constraint_type == "earliest_sequence"
    bound = _sequence_bound_value(
        constraint.parameters, constraint.constraint_type, vessel.max_foundations_per_trip
    )
    matched = _bound_targets(included, constraint.parameters)
    _mark(governing, [item.foundation_id for item in matched], constraint.name)
    by_sequence = {item.foundation.foundation_id: item.sequence for item in placements}
    bad = []
    raw = 0
    for foundation in matched:
        sequence = by_sequence.get(foundation.foundation_id)
        if sequence is None:
            bad.append(foundation.foundation_id)
            continue
        if earliest and sequence < bound:
            bad.append(foundation.foundation_id)
            raw += bound - sequence
        if not earliest and sequence > bound:
            bad.append(foundation.foundation_id)
            raw += sequence - bound
    earliest_trip = constraint.parameters.get("earliest_trip")
    if earliest and earliest_trip not in (None, ""):
        label = "Earliest trip"
        target = f"trip >= {int(earliest_trip)}"
        hard_note = "Matching locations are not installed before this trip."
        soft_note = "A soft window penalises installation before the preferred trip."
    else:
        label = "Earliest sequence" if earliest else "Latest sequence"
        target = f"{'>=' if earliest else '<='} {bound}"
        hard_note = "The sequence window is checked against the installation sequence."
        soft_note = "A soft window penalises positions outside the preferred bound."
    if constraint.enforcement == "hard":
        add(
            label,
            constraint.name,
            target,
            "Violations: " + ", ".join(bad) if bad else "Respected",
            "Failed" if bad else "Passed",
            bad,
            hard_note,
        )
        return 0, set(bad), set(), set(), set()
    max_raw = max(vessel.max_foundations_per_trip, bound) * max(len(matched), 1)
    penalty = scaled_penalty(raw, max_raw, constraint.severity or 0)
    for foundation_id in bad:
        penalties[foundation_id] += scaled_penalty(1, max_raw, constraint.severity or 0)
    add(
        f"Soft {label.lower()}",
        constraint.name,
        target,
        f"shortfall={raw}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        bad,
        soft_note,
    )
    return penalty, set(), set(), set(), set()


def _precedence(constraint, placements, add, governing, penalties):
    predecessor = str(constraint.parameters["predecessor_foundation_id"])
    successor = str(constraint.parameters["successor_foundation_id"])
    minimum_gap = int(constraint.parameters["minimum_gap"])
    maximum_gap = constraint.parameters.get("maximum_gap")
    _mark(governing, [predecessor, successor], constraint.name)
    sequences = {item.foundation.foundation_id: item.sequence for item in placements}
    gap = sequences.get(successor, 0) - sequences.get(predecessor, 0)
    short = max(0, minimum_gap - gap)
    over = 0
    if maximum_gap not in (None, ""):
        over = max(0, gap - int(maximum_gap))
    ok = short == 0 and over == 0
    affected = [] if ok else [predecessor, successor]
    if constraint.enforcement == "hard":
        add(
            "Precedence",
            constraint.name,
            f"{successor} at least {minimum_gap} after {predecessor}",
            f"Gap {gap}",
            "Passed" if ok else "Failed",
            affected,
            "Gap is the difference in installation sequence numbers.",
        )
        return 0, set(affected), set(), set(), set()
    raw = short + over
    max_raw = (
        len(placements) + minimum_gap + (len(placements) if maximum_gap not in (None, "") else 0)
    )
    penalty = scaled_penalty(raw, max_raw, constraint.severity or 0)
    for foundation_id in affected:
        penalties[foundation_id] += penalty
    add(
        "Soft precedence",
        constraint.name,
        f"Gap {minimum_gap}",
        f"gap={gap}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "A short or long gap produces a soft penalty.",
    )
    return penalty, set(), set(), set(), set()


def _count_limit(constraint, placements, vessel, *, minimum: bool, add, governing, penalties):
    matched = matching_foundations([item.foundation for item in placements], constraint.parameters)
    matched_ids = {item.foundation_id for item in matched}
    _mark(governing, sorted(matched_ids), constraint.name)
    limit = int(constraint.parameters["minimum_count" if minimum else "maximum_count"])
    trips = required_trips(len(placements), vessel.max_foundations_per_trip)
    applicable = [
        int(item) for item in constraint.parameters.get("applicable_trips") or range(1, trips + 1)
    ]
    grouped: dict[int, int] = defaultdict(int)
    for placement in placements:
        if placement.foundation.foundation_id in matched_ids:
            grouped[placement.trip] += 1
    raw = 0
    bad_trips = []
    for trip in applicable:
        count = grouped.get(trip, 0)
        if minimum and count < limit:
            raw += limit - count
            bad_trips.append(trip)
        if not minimum and count > limit:
            raw += count - limit
            bad_trips.append(trip)
    affected = [
        item.foundation.foundation_id
        for item in placements
        if item.trip in bad_trips and item.foundation.foundation_id in matched_ids
    ]
    label = "Minimum count per trip" if minimum else "Maximum count per trip"
    if constraint.enforcement == "hard":
        add(
            label,
            constraint.name,
            f"{'>=' if minimum else '<='} {limit}",
            "Trips " + ", ".join(map(str, bad_trips)) if bad_trips else "Respected",
            "Failed" if bad_trips else "Passed",
            affected,
            "Matching foundations are counted on each applicable trip.",
        )
        return 0, set(affected), set(bad_trips), set(), set()
    max_raw = (limit * len(applicable)) if minimum else max(len(matched), 1)
    penalty = scaled_penalty(raw, max(max_raw, 1), constraint.severity or 0)
    add(
        f"Soft {label.lower()}",
        constraint.name,
        f"{'>=' if minimum else '<='} {limit}",
        f"deviation={raw}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "Count deviations are penalised and do not fail a hard check.",
    )
    return penalty, set(), set(), set(), set()


def _grouping(constraint, placements, *, separate: bool, add, governing, penalties):
    identifiers = [str(item) for item in constraint.parameters["foundation_ids"]]
    _mark(governing, identifiers, constraint.name)
    trips = {item.foundation.foundation_id: item.trip for item in placements}
    pairs = []
    violations = []
    for left in range(len(identifiers)):
        for right in range(left + 1, len(identifiers)):
            pairs.append((identifiers[left], identifiers[right]))
            same = trips.get(identifiers[left]) == trips.get(identifiers[right])
            if separate and same:
                violations.append((identifiers[left], identifiers[right]))
            if not separate and not same:
                violations.append((identifiers[left], identifiers[right]))
    affected = sorted({item for pair in violations for item in pair})
    label = "Separate trip" if separate else "Same trip"
    if constraint.enforcement == "hard":
        add(
            label,
            constraint.name,
            ", ".join(identifiers),
            "Violations: " + ", ".join(f"{a}/{b}" for a, b in violations)
            if violations
            else "Respected",
            "Failed" if violations else "Passed",
            affected,
            "Hard grouping and separation are checked from the derived trip numbers.",
        )
        return 0, set(affected), set(), set(), set()
    penalty = scaled_penalty(len(violations), max(len(pairs), 1), constraint.severity or 0)
    share = penalty // max(len(affected), 1) if affected else 0
    for foundation_id in affected:
        penalties[foundation_id] += share
    add(
        f"Soft {label.lower()}",
        constraint.name,
        ", ".join(identifiers),
        f"pair_violations={len(violations)}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "Pair violations produce a soft penalty.",
    )
    return penalty, set(), set(), set(), set()


def _ordering(constraint, included, placements, vessel, add, governing, penalties):
    attribute = str(constraint.parameters["attribute"])
    direction = str(constraint.parameters["direction"])
    scope = str(constraint.parameters.get("scope") or constraint.scope or "full_sequence")
    _mark(governing, [item.foundation_id for item in included], constraint.name)
    if scope == "within_trip":
        return _window_metric(
            constraint,
            included,
            placements,
            vessel,
            attribute,
            direction,
            [
                position
                for trip in range(
                    1, required_trips(len(included), vessel.max_foundations_per_trip) + 1
                )
                for position in sequence_positions_for_trip(
                    trip, len(included), vessel.max_foundations_per_trip
                )
            ],
            per_trip=True,
            add=add,
            penalties=penalties,
            check_name="Attribute ordering",
        )
    pairs = ordering_pairs(included, attribute, direction)
    sequence_of = _sequence_by_index(included, placements)
    raw = count_inversions(sequence_of, pairs)
    if constraint.enforcement == "hard":
        add(
            "Attribute ordering",
            constraint.name,
            f"{direction} {attribute} over the full sequence",
            f"inversions={raw}",
            "Failed" if raw else "Passed",
            [item.foundation_id for item in included] if raw else [],
            "Equal attribute values are not ordered against each other.",
        )
        return 0, {item.foundation_id for item in included} if raw else set(), set(), set(), set()
    penalty = scaled_penalty(raw, max(len(pairs), 1), constraint.severity or 0)
    add(
        "Soft attribute ordering",
        constraint.name,
        f"{direction} {attribute}",
        f"inversions={raw}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        [],
        "Each inversion is normalised before severity is applied.",
    )
    return penalty, set(), set(), set(), set()


def _difficulty(constraint, included, placements, vessel, add, governing, penalties):
    attribute = str(constraint.parameters.get("attribute") or "Difficulty_Value")
    direction = str(constraint.parameters["direction"])
    _mark(governing, [item.foundation_id for item in included], constraint.name)
    positions = positions_in_trip_window(
        int(constraint.parameters["applicable_start_trip"]),
        int(constraint.parameters["applicable_end_trip"]),
        len(included),
        vessel.max_foundations_per_trip,
    )
    return _window_metric(
        constraint,
        included,
        placements,
        vessel,
        attribute,
        direction,
        positions,
        per_trip=False,
        add=add,
        penalties=penalties,
        check_name="Difficulty progression",
    )


def _window_metric(
    constraint,
    included,
    placements,
    vessel,
    attribute,
    direction,
    positions,
    *,
    per_trip: bool,
    add,
    penalties,
    check_name: str,
):
    values = attribute_values(included, attribute)
    span = attribute_span(values)
    by_sequence = {}
    index_of = {item.foundation_id: index for index, item in enumerate(included)}
    for placement in placements:
        by_sequence[placement.sequence] = values[index_of[placement.foundation.foundation_id]]
    groups = (
        [
            sequence_positions_for_trip(trip, len(included), vessel.max_foundations_per_trip)
            for trip in range(1, required_trips(len(included), vessel.max_foundations_per_trip) + 1)
        ]
        if per_trip
        else [positions]
    )
    raw = 0
    pair_count = 0
    for group in groups:
        pair_count += window_pair_count(group)
        raw += window_violation(by_sequence, group, direction)
    max_raw = span * pair_count
    if constraint.enforcement == "hard":
        add(
            check_name,
            constraint.name,
            f"{direction} {attribute}",
            f"violation={raw}",
            "Failed" if raw else "Passed",
            [item.foundation_id for item in included] if raw else [],
            "Ordering inside the selected positions was checked from the installation sequence.",
        )
        return 0, {item.foundation_id for item in included} if raw else set(), set(), set(), set()
    penalty = scaled_penalty(raw, max(max_raw, 1), constraint.severity or 0) if max_raw else 0
    add(
        f"Soft {check_name.lower()}",
        constraint.name,
        f"{direction} {attribute}",
        f"violation={raw}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        [],
        "The penalty uses the same normalisation as the solver objective.",
    )
    return penalty, set(), set(), set(), set()


def _delivery(constraint, included, placements, add, governing, penalties):
    tolerance = int(constraint.parameters["tolerance_positions"])
    _mark(governing, [item.foundation_id for item in included], constraint.name)
    sequences = {item.foundation.foundation_id: item.sequence for item in placements}
    raw = 0
    affected = []
    local_excess: dict[str, int] = {}
    for foundation in included:
        delivery = foundation.delivery_sequence or 0
        excess = delivery_excess(sequences[foundation.foundation_id], delivery, tolerance)
        local_excess[foundation.foundation_id] = excess
        if excess:
            raw += excess
            affected.append(foundation.foundation_id)
    max_raw = delivery_max_raw([item.delivery_sequence or 1 for item in included], tolerance)
    if constraint.enforcement == "hard":
        add(
            "Delivery-sequence alignment",
            constraint.name,
            f"Tolerance {tolerance}",
            f"excess={raw}",
            "Failed" if raw else "Passed",
            affected,
            "Deviation inside the tolerance is accepted.",
        )
        return 0, set(affected), set(), set(), set()
    penalty = scaled_penalty(raw, max(max_raw, 1), constraint.severity or 0) if max_raw else 0
    for foundation_id, excess in local_excess.items():
        penalties[foundation_id] += scaled_penalty(
            excess, max(max_raw, 1), constraint.severity or 0
        )
    add(
        "Soft delivery-sequence alignment",
        constraint.name,
        f"Tolerance {tolerance}",
        f"excess={raw}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "Deviation outside the tolerance is penalised by severity. It is not a hard failure.",
    )
    return penalty, set(), set(), set(), set()


def _installed_first(constraint, placements, add, governing, penalties):
    matched = matching_foundations([item.foundation for item in placements], constraint.parameters)
    matched_ids = {item.foundation_id for item in matched}
    _mark(governing, sorted(matched_ids), constraint.name)
    count = len(matched_ids)
    late = [
        item
        for item in placements
        if item.foundation.foundation_id in matched_ids and item.sequence > count
    ]
    affected = [item.foundation.foundation_id for item in late]
    if count == 0:
        add(
            "Matching locations first",
            constraint.name,
            "No matching locations",
            "Nothing to place first",
            "Passed",
            [],
            "The rule does not change the sequence when no location matches.",
        )
        return _empty()
    if constraint.enforcement == "hard":
        add(
            "Matching locations first",
            constraint.name,
            f"Matching locations in positions 1 to {count}, in any order",
            "Respected" if not late else "Late: " + ", ".join(affected),
            "Passed" if not late else "Failed",
            affected,
            "Matching locations fill the first positions. Their order inside that block is free.",
        )
        return 0, set(affected), set(), set(), set()
    raw = sum(item.sequence - count for item in late)
    max_raw = max(count * len(placements), 1)
    penalty = scaled_penalty(raw, max_raw, constraint.severity or 0) if raw else 0
    for foundation_id in affected:
        penalties[foundation_id] += penalty
    add(
        "Soft matching locations first",
        constraint.name,
        f"Prefer matches in positions 1 to {count}",
        f"late={len(late)}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "A matching location after the first block produces a soft penalty.",
    )
    return penalty, set(), set(), set(), set()


def _avoid_first_trips(constraint, placements, vessel, add, governing, penalties):
    matched = matching_foundations([item.foundation for item in placements], constraint.parameters)
    matched_ids = {item.foundation_id for item in matched}
    _mark(governing, sorted(matched_ids), constraint.name)
    trip_count = int(constraint.parameters["trip_count"])
    earliest = trip_count * vessel.max_foundations_per_trip + 1
    early = [
        item
        for item in placements
        if item.foundation.foundation_id in matched_ids and item.sequence < earliest
    ]
    affected = [item.foundation.foundation_id for item in early]
    target = f"Matching locations at sequence {earliest} or later (after trip {trip_count})"
    if constraint.enforcement == "hard":
        add(
            "Avoid matches in the first trips",
            constraint.name,
            target,
            "Respected" if not early else "Early: " + ", ".join(affected),
            "Passed" if not early else "Failed",
            affected,
            "Matching locations are not installed during the opening trips.",
        )
        return 0, set(affected), set(), set(), set()
    raw = sum(earliest - item.sequence for item in early)
    max_raw = max((earliest - 1) * max(len(matched_ids), 1), 1)
    penalty = scaled_penalty(raw, max_raw, constraint.severity or 0) if raw else 0
    for foundation_id in affected:
        penalties[foundation_id] += penalty
    add(
        "Soft avoid matches in the first trips",
        constraint.name,
        target,
        f"early={len(early)}; penalty={penalty}",
        "Soft trade-off" if penalty else "Passed",
        affected,
        "A matching location in the opening trips produces a soft penalty. It is not a hard failure.",
    )
    return penalty, set(), set(), set(), set()


def _distance(constraint, placements, vessel, add, governing):
    _mark(governing, [item.foundation.foundation_id for item in placements], constraint.name)
    distance = _route_distance(placements, constraint, vessel)
    ordered = sorted(placements, key=lambda item: item.sequence)
    sailing = sum(
        metres_between(left.foundation, right.foundation)
        for left, right in zip(ordered, ordered[1:], strict=False)
    )
    add(
        "Total sailing distance",
        constraint.name,
        "Sum of every consecutive foundation-to-foundation leg",
        format_nautical_miles(sailing),
        "Information",
        [],
        "This is the solver objective. It includes the sail inside each trip and the sail "
        "from the end of one trip to the start of the next. Harbour transit is not included. "
        "There is no maximum distance, so the nautical miles are information and are not a "
        "pass or fail limit.",
    )
    add(
        "Within-trip distance",
        constraint.name,
        "Sailing that stays inside trips",
        format_nautical_miles(distance),
        "Information",
        [],
        "This is the part of the sailing total that stays inside trips. The objective also "
        "includes the sail from the end of one trip to the start of the next.",
    )
    return _empty()


def _route_distance(
    placements: list[_Placement], constraint: ConstraintInput, vessel: VesselConfig
) -> int:
    del constraint, vessel
    total = 0
    grouped: dict[int, list[_Placement]] = defaultdict(list)
    for placement in placements:
        grouped[placement.trip].append(placement)
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: item.position)
        for left, right in zip(ordered, ordered[1:], strict=False):
            total += metres_between(left.foundation, right.foundation)
    return total


def _sequence_by_index(included: list[FoundationInput], placements: list[_Placement]) -> list[int]:
    sequences = {item.foundation.foundation_id: item.sequence for item in placements}
    return [sequences[item.foundation_id] for item in included]


def _sequence_rows(
    placements, penalties, governing, failed_ids, structural_ok: bool
) -> list[SequenceRow]:
    if not placements:
        return []
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for placement in placements:
        totals[placement.trip] += placement.foundation.weight_t or Decimal("0")
    rows: list[SequenceRow] = []
    for placement in placements:
        foundation = placement.foundation
        deviation = None
        if foundation.delivery_sequence is not None:
            deviation = placement.sequence - foundation.delivery_sequence
        rows.append(
            SequenceRow(
                installation_sequence=placement.sequence,
                trip=placement.trip,
                vessel_position=placement.position,
                foundation_id=foundation.foundation_id,
                weight_t=foundation.weight_t,
                trip_total_weight_t=totals[placement.trip],
                delivery_sequence=foundation.delivery_sequence,
                sequence_deviation=deviation,
                delivery_batch=foundation.delivery_batch,
                difficulty_value=foundation.difficulty_value,
                punch_through=foundation.punch_through,
                fixed_trip=foundation.fixed_trip,
                fixed_position=foundation.fixed_position,
                earliest_sequence=foundation.earliest_sequence,
                latest_sequence=foundation.latest_sequence,
                hard_constraint_status="Failed"
                if not structural_ok or foundation.foundation_id in failed_ids
                else "Passed",
                soft_penalty=penalties.get(foundation.foundation_id, 0),
                governing_constraints="; ".join(governing.get(foundation.foundation_id, [])),
                notes=foundation.notes,
            )
        )
    return rows


def _trip_rows(
    placements,
    constraints,
    vessel: VesselConfig,
    payload_failed: set[int],
    payload_soft: set[int],
    position_failed: set[int],
    structural_ok: bool,
) -> list[TripRow]:
    if not structural_ok or not placements:
        return []
    grouped: dict[int, list[_Placement]] = defaultdict(list)
    for placement in placements:
        grouped[placement.trip].append(placement)
    payload_limits = [
        Decimal(str(item.parameters["maximum_payload_t"]))
        for item in constraints
        if item.constraint_type == "maximum_trip_payload" and item.enforcement == "hard"
    ]
    if not payload_limits:
        payload_limits = [
            Decimal(str(item.parameters["maximum_payload_t"]))
            for item in constraints
            if item.constraint_type == "maximum_trip_payload"
        ]
    limit = min(payload_limits) if payload_limits else None
    distance_constraint = next(
        (item for item in constraints if item.constraint_type == "minimise_within_trip_distance"),
        None,
    )
    rows: list[TripRow] = []
    for trip, group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda item: item.position)
        total = sum((item.foundation.weight_t or Decimal("0")) for item in ordered)
        difficulties = [
            item.foundation.difficulty_value
            for item in ordered
            if item.foundation.difficulty_value is not None
        ]
        average = None
        maximum = None
        if difficulties:
            average = (sum(difficulties) / Decimal(len(difficulties))).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            maximum = max(difficulties)
        route = None
        if distance_constraint is not None:
            route = Decimal(_route_distance(ordered, distance_constraint, vessel))
        if trip in payload_failed:
            payload_check = "Failed"
        elif trip in payload_soft:
            payload_check = "Soft trade-off"
        elif limit is None:
            payload_check = "Information"
        else:
            payload_check = "Passed"
        position_check = "Failed" if trip in position_failed else "Passed"
        if payload_check == "Failed" or position_check == "Failed":
            overall = "Failed"
        elif payload_check == "Soft trade-off":
            overall = "Soft trade-off"
        else:
            overall = "Passed"
        rows.append(
            TripRow(
                trip=trip,
                foundation_count=len(ordered),
                foundations_in_order=", ".join(item.foundation.foundation_id for item in ordered),
                payload_limit_t=limit,
                total_weight_t=total,
                remaining_payload_t=None if limit is None else limit - total,
                punch_through_count=sum(
                    1 for item in ordered if item.foundation.punch_through is True
                ),
                average_difficulty=average,
                maximum_difficulty=maximum,
                route_distance=route,
                payload_check=payload_check,
                position_check=position_check,
                overall_trip_check=overall,
            )
        )
    return rows
