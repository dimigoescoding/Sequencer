"""Shortest route inside a trip after the solver has chosen its locations.

Trip membership stays as the solver left it. Only the order of those locations
changes, and only when the new order still satisfies every active hard constraint.
"""

from __future__ import annotations

from itertools import permutations

from apps.optimisation.services.evaluation import evaluate
from apps.optimisation.services.geometry import required_trips, sequence_positions_for_trip
from apps.optimisation.services.routing import harbour_coordinates, metres_between, metres_xy
from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig

# 7! is 5,040. Larger trips use an exact shortest path and keep the solver
# order when that path would break a hard constraint.
_EXACT_PERMUTATION_LIMIT = 7


def optimise_within_trip_routes(
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
    if not order or not active:
        return list(order)
    rule = min(active, key=lambda item: (item.display_order, item.constraint_id or 0))
    by_id = {item.foundation_id: item for item in foundations}
    capacity = vessel.max_foundations_per_trip
    current = list(order)
    for trip in range(1, required_trips(len(current), capacity) + 1):
        slots = [
            position - 1 for position in sequence_positions_for_trip(trip, len(current), capacity)
        ]
        members = [current[slot] for slot in slots]
        if len(members) <= 1:
            continue
        chosen = _best_order(members, current, slots, by_id, foundations, vessel, constraints, rule)
        for slot, name in zip(slots, chosen, strict=True):
            current[slot] = name
    return current


def _best_order(
    members: list[str],
    current: list[str],
    slots: list[int],
    by_id: dict[str, FoundationInput],
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    rule: ConstraintInput,
) -> list[str]:
    if len(members) <= _EXACT_PERMUTATION_LIMIT:
        candidates = permutations(members)
    else:
        candidates = (members, _held_karp(members, by_id, rule, vessel))
    best = list(members)
    best_cost = _path_cost(best, by_id, rule, vessel)
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        ordered = tuple(candidate)
        if ordered in seen:
            continue
        seen.add(ordered)
        trial = list(current)
        for slot, name in zip(slots, ordered, strict=True):
            trial[slot] = name
        if not _hard_rules_hold(foundations, vessel, constraints, trial):
            continue
        cost = _path_cost(list(ordered), by_id, rule, vessel)
        if cost < best_cost:
            best = list(ordered)
            best_cost = cost
    return best


def _hard_rules_hold(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    order: list[str],
) -> bool:
    return evaluate(foundations, vessel, constraints, order).validation_status == "Passed"


def _path_cost(
    names: list[str],
    by_id: dict[str, FoundationInput],
    rule: ConstraintInput,
    vessel: VesselConfig,
) -> int:
    points = [by_id[name] for name in names]
    total = sum(
        metres_between(left, right) for left, right in zip(points, points[1:], strict=False)
    )
    harbour = harbour_coordinates(rule.parameters, vessel)
    if harbour is not None and points:
        easting, northing = harbour
        total += metres_xy(points[0].easting_m, points[0].northing_m, easting, northing)
        total += metres_xy(points[-1].easting_m, points[-1].northing_m, easting, northing)
    return total


def _held_karp(
    names: list[str],
    by_id: dict[str, FoundationInput],
    rule: ConstraintInput,
    vessel: VesselConfig,
) -> tuple[str, ...]:
    points = [by_id[name] for name in names]
    count = len(points)
    distance = [
        [metres_between(points[left], points[right]) for right in range(count)]
        for left in range(count)
    ]
    harbour = harbour_coordinates(rule.parameters, vessel)
    harbour_leg = [0] * count
    if harbour is not None:
        easting, northing = harbour
        harbour_leg = [
            metres_xy(point.easting_m, point.northing_m, easting, northing) for point in points
        ]
    size = 1 << count
    infinite = 10**18
    cost = [[infinite] * count for _ in range(size)]
    previous = [[-1] * count for _ in range(size)]
    for start in range(count):
        cost[1 << start][start] = harbour_leg[start]
    for mask in range(size):
        for last in range(count):
            current = cost[mask][last]
            if current >= infinite or mask & (1 << last) == 0:
                continue
            for nxt in range(count):
                if mask & (1 << nxt):
                    continue
                nxt_mask = mask | (1 << nxt)
                candidate = current + distance[last][nxt]
                if candidate < cost[nxt_mask][nxt]:
                    cost[nxt_mask][nxt] = candidate
                    previous[nxt_mask][nxt] = last
    full = size - 1
    end = min(range(count), key=lambda index: cost[full][index] + harbour_leg[index])
    order: list[int] = []
    mask = full
    while end != -1:
        order.append(end)
        prior = previous[mask][end]
        mask ^= 1 << end
        end = prior
    order.reverse()
    return tuple(names[index] for index in order)
