"""Second step: minimise the sail from the end of one trip to the start of the next.

Trip membership stays as the within-trip search left it. A trip may be reversed,
and trips may change places, only when that keeps the within-trip distance and
still satisfies the active hard constraints.
"""

from __future__ import annotations

from collections.abc import Callable

from apps.constraints.services.matching import matching_foundations
from apps.optimisation.services.evaluation import evaluate
from apps.optimisation.services.routing import harbour_coordinates, metres_between, metres_xy
from apps.optimisation.services.solver import _bound_targets, _sequence_bound_value
from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig

# 2^16 trip subsets is the largest exact search kept here.
_EXACT_BLOCK_LIMIT = 16
_Check = Callable[[str, int, int], bool]


def optimise_trip_connections(
    order: list[str],
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
) -> list[str]:
    active = [
        item
        for item in constraints
        if item.active and item.constraint_type == "minimise_within_trip_distance"
    ]
    capacity = vessel.max_foundations_per_trip
    if not order or not active or capacity < 1 or len(order) <= capacity:
        return list(order)
    by_id = {item.foundation_id: item for item in foundations}
    if any(name not in by_id for name in order):
        return list(order)
    blocks = [order[index : index + capacity] for index in range(0, len(order), capacity)]
    if len(blocks) > _EXACT_BLOCK_LIMIT:
        return list(order)
    harbour = harbour_coordinates(active[0].parameters, vessel)
    oriented = [_orientations(block, by_id, harbour) for block in blocks]
    allowed = _allowed_slots(oriented, foundations, vessel, constraints, len(order))
    if any(index not in allowed[index][0] for index, _block in enumerate(blocks)):
        return list(order)
    chosen = _shortest_links(oriented, allowed, by_id)
    if chosen is None or _link_cost(chosen, capacity, by_id) >= _link_cost(order, capacity, by_id):
        return list(order)
    if evaluate(foundations, vessel, constraints, chosen).validation_status != "Passed":
        return list(order)
    return chosen


def _orientations(
    block: list[str],
    by_id: dict[str, FoundationInput],
    harbour: tuple | None,
) -> list[list[str]]:
    forward = list(block)
    reverse = list(reversed(block))
    if _block_metres(reverse, by_id, harbour) <= _block_metres(forward, by_id, harbour):
        return [forward, reverse]
    return [forward, []]


def _block_metres(
    block: list[str],
    by_id: dict[str, FoundationInput],
    harbour: tuple | None,
) -> int:
    if not block:
        return 0
    total = sum(
        metres_between(by_id[left], by_id[right])
        for left, right in zip(block, block[1:], strict=False)
    )
    if harbour is not None:
        easting, northing = harbour
        total += metres_xy(by_id[block[0]].easting_m, by_id[block[0]].northing_m, easting, northing)
        total += metres_xy(
            by_id[block[-1]].easting_m, by_id[block[-1]].northing_m, easting, northing
        )
    return total


def _allowed_slots(
    oriented: list[list[list[str]]],
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    count: int,
) -> list[list[set[int]]]:
    capacity = vessel.max_foundations_per_trip
    slot_count = len(oriented)
    checks = _position_checks(foundations, vessel, constraints)
    partial = count % capacity != 0
    allowed: list[list[set[int]]] = []
    for orientations in oriented:
        block_slots: list[set[int]] = []
        for members in orientations:
            if not members:
                block_slots.append(set())
                continue
            legal = set()
            for slot in range(slot_count):
                is_last = slot == slot_count - 1
                short = len(members) < capacity
                if partial and short != is_last:
                    continue
                if _members_fit(members, slot, capacity, checks):
                    legal.add(slot)
            block_slots.append(legal)
        if len(block_slots) == 1:
            block_slots.append(set())
        allowed.append(block_slots)
    return allowed


def _members_fit(members: list[str], slot: int, capacity: int, checks: list[_Check]) -> bool:
    for index, name in enumerate(members):
        position = slot * capacity + index + 1
        trip = slot + 1
        if any(not check(name, position, trip) for check in checks):
            return False
    return True


def _position_checks(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
) -> list[_Check]:
    included = [item for item in foundations if item.include]
    capacity = vessel.max_foundations_per_trip
    checks: list[_Check] = []
    for constraint in constraints:
        if not constraint.active or constraint.enforcement != "hard":
            continue
        kind = constraint.constraint_type
        if kind == "matching_installed_first":
            matched = {
                item.foundation_id for item in matching_foundations(included, constraint.parameters)
            }
            checks.append(_installed_first(matched, len(matched)))
        elif kind in {"earliest_sequence", "latest_sequence"}:
            bound = _sequence_bound_value(constraint.parameters, kind, capacity)
            matched = {
                item.foundation_id for item in _bound_targets(included, constraint.parameters)
            }
            checks.append(_window(matched, bound, earliest=kind == "earliest_sequence"))
        elif kind == "fixed_trip":
            checks.append(
                _fixed_trip(
                    str(constraint.parameters.get("foundation_id") or ""),
                    int(constraint.parameters["trip_number"]),
                )
            )
        elif kind == "fixed_vessel_position":
            trip_number = constraint.parameters.get("trip_number")
            checks.append(
                _fixed_position(
                    str(constraint.parameters.get("foundation_id") or ""),
                    int(constraint.parameters["position_number"]),
                    None if trip_number in (None, "") else int(trip_number),
                    capacity,
                )
            )
    return checks


def _installed_first(matched: set[str], limit: int) -> _Check:
    def check(name: str, position: int, trip: int) -> bool:
        del trip
        if name in matched:
            return position <= limit
        return position > limit

    return check


def _window(matched: set[str], bound: int, *, earliest: bool) -> _Check:
    def check(name: str, position: int, trip: int) -> bool:
        del trip
        if name not in matched:
            return True
        if earliest:
            return position >= bound
        return position <= bound

    return check


def _fixed_trip(foundation_id: str, trip_number: int) -> _Check:
    def check(name: str, position: int, trip: int) -> bool:
        del position
        if name != foundation_id:
            return True
        return trip == trip_number

    return check


def _fixed_position(
    foundation_id: str,
    position_number: int,
    trip_number: int | None,
    capacity: int,
) -> _Check:
    def check(name: str, position: int, trip: int) -> bool:
        if name != foundation_id:
            return True
        if ((position - 1) % capacity) + 1 != position_number:
            return False
        if trip_number is not None and trip != trip_number:
            return False
        return True

    return check


def _shortest_links(
    oriented: list[list[list[str]]],
    allowed: list[list[set[int]]],
    by_id: dict[str, FoundationInput],
) -> list[str] | None:
    block_count = len(oriented)
    full = (1 << block_count) - 1
    inf = 10**18
    cost = [[inf, inf] for _ in range(block_count)]
    costs = [cost]
    # costs[mask][block][orientation]
    table: list[list[list[int]]] = [
        [[inf, inf] for _ in range(block_count)] for _ in range(full + 1)
    ]
    parent: list[list[list[tuple[int, int, int] | None]]] = [
        [[None, None] for _ in range(block_count)] for _ in range(full + 1)
    ]
    del costs
    for block in range(block_count):
        for orientation in range(2):
            if 0 in allowed[block][orientation]:
                table[1 << block][block][orientation] = 0
    for mask in range(full + 1):
        placed = mask.bit_count()
        if placed == 0 or placed == block_count:
            continue
        for last in range(block_count):
            if mask & (1 << last) == 0:
                continue
            for orientation in range(2):
                base = table[mask][last][orientation]
                if base >= inf:
                    continue
                leave = oriented[last][orientation][-1]
                for nxt in range(block_count):
                    bit = 1 << nxt
                    if mask & bit:
                        continue
                    for nxt_orientation in range(2):
                        if placed not in allowed[nxt][nxt_orientation]:
                            continue
                        arrive = oriented[nxt][nxt_orientation][0]
                        candidate = base + metres_between(by_id[leave], by_id[arrive])
                        nxt_mask = mask | bit
                        if candidate < table[nxt_mask][nxt][nxt_orientation]:
                            table[nxt_mask][nxt][nxt_orientation] = candidate
                            parent[nxt_mask][nxt][nxt_orientation] = (mask, last, orientation)
    best: tuple[int, int] | None = None
    best_cost = inf
    for block in range(block_count):
        for orientation in range(2):
            if table[full][block][orientation] < best_cost:
                best_cost = table[full][block][orientation]
                best = (block, orientation)
    if best is None or best_cost >= inf:
        return None
    parts: list[list[str]] = []
    mask = full
    block, orientation = best
    while True:
        parts.append(oriented[block][orientation])
        previous = parent[mask][block][orientation]
        if previous is None:
            break
        mask, block, orientation = previous
    sequence: list[str] = []
    for part in reversed(parts):
        sequence.extend(part)
    return sequence


def _link_cost(order: list[str], capacity: int, by_id: dict[str, FoundationInput]) -> int:
    total = 0
    blocks = [order[index : index + capacity] for index in range(0, len(order), capacity)]
    for left, right in zip(blocks, blocks[1:], strict=False):
        if left and right:
            total += metres_between(by_id[left[-1]], by_id[right[0]])
    return total
