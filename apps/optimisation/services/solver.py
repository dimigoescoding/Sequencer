"""CP-SAT model for the foundation installation sequence.

The only decision is the global sequence. Trip number and vessel position are
derived from that sequence. Hard constraints are added to the model. Soft
constraints become scaled penalty terms. Hard constraints are never dropped.
"""

from __future__ import annotations

import time
from dataclasses import replace
from decimal import Decimal
from typing import Any

from ortools.sat.python import cp_model

from apps.constraints.services.matching import loop_blocks, matching_foundations, string_blocks
from apps.optimisation.services.buffer import (
    DAY_SECONDS,
    PREVIOUS,
    buffer_problem,
    location_links,
    package_name,
    slot_instants,
    worst_shortfall,
)
from apps.optimisation.services.cancellation import bind, release, was_cancelled
from apps.optimisation.services.geometry import (
    positions_in_trip_window,
    required_trips,
    sequence_positions_for_trip,
)
from apps.optimisation.services.metrics import (
    attribute_span,
    attribute_values,
    delivery_max_raw,
    ordering_pairs,
    window_pair_count,
)
from apps.optimisation.services.routing import metres_between
from apps.optimisation.services.scaling import (
    NORM,
    SOLVER_SEED,
    weight_kg,
)
from apps.optimisation.services.types import (
    CampaignResult,
    ConstraintInput,
    FoundationInput,
    VesselConfig,
)


def solve_order(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
) -> tuple[str, int | None, float, str, list[str]]:
    included = [item for item in foundations if item.include]
    active = [item for item in constraints if item.active]
    started = time.perf_counter()
    limit = max(vessel.solver_time_limit_seconds, 1)
    distance = next(
        (item for item in active if item.constraint_type == "minimise_within_trip_distance"),
        None,
    )
    if distance is not None and len(included) > 12 and limit >= 8:
        status, objective, order, bound = _search_complete_path(
            foundations, vessel, active, included, distance, limit, started
        )
        runtime = time.perf_counter() - started
        if status == "CANCELLED" or was_cancelled():
            return _cancelled(runtime)
        message = _distance_message(status, active, included, vessel, order, bound)
        return status, objective, runtime, message, order
    hint = _starting_route(foundations, vessel, active, included, limit, started)
    remaining = max(1, limit - int(time.perf_counter() - started))
    builder = _Builder(
        included, replace(vessel, solver_time_limit_seconds=remaining), constraints=active
    )
    for constraint in active:
        builder.add_constraint(constraint)
    if hint:
        builder.hint(hint)
    status, objective, order = builder.solve()
    runtime = time.perf_counter() - started
    if status == "CANCELLED" or was_cancelled():
        return _cancelled(runtime)
    status, objective, order = _shorter_sailing(
        foundations, vessel, active, included, hint, status, objective, order
    )
    runtime = time.perf_counter() - started
    if was_cancelled():
        return _cancelled(runtime)
    message = _status_message(status, active)
    return status, objective, runtime, message, order


def solve_programme(
    foundations: list[FoundationInput],
    cables: list[FoundationInput],
    turbines: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
    programme: dict | None = None,
) -> tuple[str, int | None, float, str, list[CampaignResult]]:
    """Solve FOU, IAC, and WTG in one model when more than foundations are included.

    A foundation-only campaign keeps the existing search, including the longer
    sailing-distance search. Packages do not impose an order on each other
    unless a package buffer is active.
    """
    started = time.perf_counter()
    fou_items = [item for item in foundations if item.include]
    iac_items = [item for item in cables if item.include]
    wtg_items = [item for item in turbines if item.include]
    grouped = {
        "FOU": [item for item in constraints if _package(item) == "FOU"],
        "IAC": [item for item in constraints if _package(item) == "IAC"],
        "WTG": [item for item in constraints if _package(item) == "WTG"],
    }
    if not fou_items and not iac_items and not wtg_items:
        return (
            "ERROR",
            None,
            time.perf_counter() - started,
            "No included FOU, IAC, or WTG activities are available to sequence.",
            [],
        )
    groups = {"FOU": fou_items, "IAC": iac_items, "WTG": wtg_items}
    calendar = programme or {}
    problems = buffer_problem(constraints, groups, calendar)
    if problems:
        return ("ERROR", None, time.perf_counter() - started, " ".join(problems), [])
    if not iac_items and not wtg_items:
        status, objective, runtime, message, order = solve_order(
            foundations, vessel, grouped["FOU"]
        )
        return (
            status,
            objective,
            runtime,
            message,
            [
                CampaignResult(
                    "FOU",
                    fou_items,
                    order,
                    vessel,
                    [item for item in grouped["FOU"] if item.active],
                )
            ],
        )

    model = cp_model.CpModel()
    builders: list[_Builder] = []
    plans: list[tuple[str, list[FoundationInput], VesselConfig, list[ConstraintInput]]] = []
    if fou_items:
        _add_campaign(model, builders, plans, "FOU", fou_items, vessel, grouped["FOU"], "fou")
    if iac_items:
        _add_campaign(
            model,
            builders,
            plans,
            "IAC",
            iac_items,
            replace(vessel, max_foundations_per_trip=len(iac_items)),
            grouped["IAC"],
            "iac",
        )
    if wtg_items:
        _add_campaign(
            model,
            builders,
            plans,
            "WTG",
            wtg_items,
            replace(vessel, max_foundations_per_trip=max(vessel.wtg_per_trip, 1)),
            grouped["WTG"],
            "wtg",
        )
    by_package = {package: builder for builder, (package, *_rest) in zip(builders, plans)}
    buffered = _apply_package_buffers(model, by_package, groups, constraints, calendar)
    terms = _combined_objective(builders)
    if terms:
        model.Minimize(sum(terms))
    solver = _solver(vessel.solver_time_limit_seconds)
    status = _run_solver(solver, model)
    runtime = time.perf_counter() - started
    if status == "CANCELLED":
        return (*_cancelled(runtime),)
    active = [item for item in constraints if item.active]
    message = _status_message(status, active)
    programme_note = (
        "Programme dates set the package buffer. No other package order was added."
        if buffered
        else "No package order or buffer was added."
    )
    message = (
        message
        + " The included packages were solved together as one programme. "
        + programme_note
    )
    if status not in {"OPTIMAL", "FEASIBLE"}:
        return status, None, runtime, message, []
    campaigns: list[CampaignResult] = []
    for builder, (package, items, package_vessel, package_constraints) in zip(
        builders, plans, strict=True
    ):
        order = builder.read_order(solver)
        if any(item == "" for item in order):
            return (
                "ERROR",
                None,
                runtime,
                "The solver model could not be solved. No sequence was created.",
                [],
            )
        campaigns.append(
            CampaignResult(
                package,
                items,
                order,
                package_vessel,
                [item for item in package_constraints if item.active],
            )
        )
    objective = int(round(solver.ObjectiveValue())) if terms else 0
    return status, objective, runtime, message, campaigns


def _package(constraint: ConstraintInput) -> str:
    package = str(getattr(constraint, "package", "") or "FOU").strip().upper()
    if package not in {"FOU", "IAC", "WTG"}:
        return "FOU"
    return package


def _add_campaign(model, builders, plans, package, items, vessel, constraints, prefix) -> None:
    active = [item for item in constraints if item.active]
    builder = _Builder(items, vessel, model=model, name_prefix=prefix, constraints=active)
    for constraint in active:
        builder.add_constraint(constraint)
    builders.append(builder)
    plans.append((package, items, vessel, constraints))


def _apply_package_buffers(model, by_package, groups, constraints, calendar) -> bool:
    applied = False
    for constraint in constraints:
        if not constraint.active or constraint.constraint_type != "package_buffer":
            continue
        later_name = package_name(constraint)
        earlier_name = PREVIOUS[later_name]
        later = by_package[later_name]
        earlier = by_package[earlier_name]
        links = location_links(later_name, groups)
        applied = True
        if not links:
            continue
        ends = slot_instants(calendar, earlier_name, earlier.n, "end")
        starts = slot_instants(calendar, later_name, later.n, "start")
        if ends is None or starts is None:
            continue
        mode = constraint.parameters.get("mode")
        if mode == "minimum" and constraint.enforcement == "hard":
            days = int(constraint.parameters["minimum_days"])
            _forbid_short_gaps(model, earlier, later, ends, starts, links, days)
            continue
        if mode == "minimum":
            _penalise_short_gaps(earlier, later, ends, starts, links, constraint)
            continue
        _maximize_gaps(model, earlier, later, ends, starts, links, constraint)
    return applied


def _forbid_short_gaps(model, earlier, later, ends, starts, links, days: int) -> None:
    minimum = days * DAY_SECONDS
    for _location, lefts, rights in links:
        for left in lefts:
            for right in rights:
                for position, end in enumerate(ends):
                    for slot, start in enumerate(starts):
                        if start - end < minimum:
                            model.Add(earlier.x[left][position] + later.x[right][slot] <= 1)


def _penalise_short_gaps(earlier, later, ends, starts, links, constraint) -> None:
    minimum = int(constraint.parameters["minimum_days"]) * DAY_SECONDS
    limit = worst_shortfall(ends, starts, minimum)
    if limit <= 0:
        return
    shorts = []
    for _location, lefts, rights in links:
        pieces = []
        for left in lefts:
            for right in rights:
                short = earlier._int(0, limit, "buffer")
                later_at = _assigned_instant(later, right, starts)
                earlier_at = _assigned_instant(earlier, left, ends)
                earlier.model.Add(short >= minimum - later_at + earlier_at)
                pieces.append(short)
        if len(pieces) == 1:
            shorts.append(pieces[0])
            continue
        worst = earlier._int(0, limit, "buffer")
        for piece in pieces:
            earlier.model.Add(worst >= piece)
        shorts.append(worst)
    if shorts:
        earlier._penalise(sum(shorts), limit * len(shorts), constraint.severity)


def _maximize_gaps(model, earlier, later, ends, starts, links, constraint) -> None:
    low = min(starts) - max(ends)
    high = max(starts) - min(ends)
    least = model.NewIntVar(low, high, earlier._name("buffer"))
    for _location, lefts, rights in links:
        for left in lefts:
            for right in rights:
                later_at = _assigned_instant(later, right, starts)
                earlier_at = _assigned_instant(earlier, left, ends)
                model.Add(least <= later_at - earlier_at)
    deficit = high - least
    if constraint.enforcement == "hard":
        earlier.hard_distance_terms.append(deficit)
        return
    earlier._penalise(deficit, max(high - low, 1), constraint.severity)


def _assigned_instant(builder, index: int, instants: list[int]):
    return sum(instants[position] * builder.x[index][position] for position in range(builder.n))


def _combined_objective(builders: list[_Builder]) -> list[Any]:
    soft: list[Any] = []
    hard: list[Any] = []
    for builder in builders:
        soft.extend(builder.objective_terms)
        hard.extend(builder.hard_distance_terms)
    terms = list(soft)
    if hard:
        weight = len(soft) * 100 * NORM + 1
        terms.extend(weight * raw for raw in hard)
    return terms


def _cancelled(runtime: float):
    return (
        "CANCELLED",
        None,
        runtime,
        "The run was cancelled. No sequence was stored.",
        [],
    )


def _run_solver(solver: cp_model.CpSolver, model: cp_model.CpModel) -> str:
    bind(solver)
    try:
        code = solver.Solve(model)
    finally:
        release(solver)
    if was_cancelled():
        return "CANCELLED"
    return _status_code(code)


def _solver(time_limit: int) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max(time_limit, 1))
    solver.parameters.random_seed = SOLVER_SEED
    solver.parameters.num_search_workers = 1
    solver.parameters.repair_hint = True
    return solver


def _status_code(code: int) -> str:
    return {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "ERROR",
    }.get(code, "ERROR")


def _starting_route(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    included: list[FoundationInput],
    limit: int,
    started: float,
) -> list[str]:
    """Find a feasible route before the sailing-distance search starts."""
    if not any(item.constraint_type == "minimise_within_trip_distance" for item in active):
        return []
    structural = [
        item for item in active if item.constraint_type != "minimise_within_trip_distance"
    ]
    hint_limit = min(5, limit)
    _status, _objective, _runtime, _message, hint = solve_order(
        foundations,
        replace(vessel, solver_time_limit_seconds=hint_limit),
        structural,
    )
    elapsed = time.perf_counter() - started
    remaining = limit - elapsed
    if remaining < 10 or len(included) <= 12:
        return hint
    warm_limit = min(15, max(5, int(remaining) // 5))
    warm = _Builder(
        included, replace(vessel, solver_time_limit_seconds=warm_limit), constraints=active
    )
    for constraint in active:
        if constraint.constraint_type == "minimise_within_trip_distance":
            warm.add_within_trip_start(constraint)
        else:
            warm.add_constraint(constraint)
    if hint:
        warm.hint(hint)
    _status, _objective, warm_order = warm.solve()
    if not warm_order:
        return hint
    from apps.optimisation.services.between_trips import optimise_trip_connections

    return optimise_trip_connections(warm_order, foundations, vessel, active)


def _search_complete_path(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    included: list[FoundationInput],
    distance: ConstraintInput,
    limit: int,
    started: float,
) -> tuple[str, int | None, list[str], int]:
    """Minimise the full sailing path by re-solving consecutive stretches."""
    hint = _starting_route(foundations, vessel, active, included, limit, started)
    greedy = _greedy_route(foundations, vessel, active, included)
    order = _shorter_order(included, hint, greedy)
    if not order:
        return "UNKNOWN", None, [], 0
    matrix = [
        [metres_between(included[left], included[right]) for right in range(len(included))]
        for left in range(len(included))
    ]
    deadline = started + limit
    capacity = max(vessel.max_foundations_per_trip, 1)
    widths = [min(len(included), capacity * multiple) for multiple in (1, 2, 3, 4, 5)]
    widths = [width for width in dict.fromkeys(widths) if width >= 2]
    shift = 0
    while time.perf_counter() < deadline - 0.3 and not was_cancelled():
        for left, width in _longest_leg_windows(order, included, matrix, capacity):
            if was_cancelled() or time.perf_counter() >= deadline - 0.3:
                break
            right = min(len(included), left + width)
            slice_limit = min(4.0, deadline - time.perf_counter())
            if slice_limit < 0.2 or right - left < 2:
                break
            candidate = _reoptimize_window(
                included, vessel, active, distance, order, left, right, matrix, slice_limit
            )
            order = _shorter_order(included, order, candidate)
        for width in widths:
            if was_cancelled():
                break
            step = max(1, min(capacity, width // 2))
            for left in range(shift % step, len(included) - 1, step):
                if was_cancelled() or time.perf_counter() >= deadline - 0.3:
                    break
                right = min(len(included), left + width)
                if right - left < 2:
                    continue
                slice_limit = min(
                    3.0 if width <= capacity * 2 else 5.0, deadline - time.perf_counter()
                )
                if slice_limit < 0.2:
                    break
                candidate = _reoptimize_window(
                    included, vessel, active, distance, order, left, right, matrix, slice_limit
                )
                order = _shorter_order(included, order, candidate)
        shift += max(1, capacity // 2)
    metres = _sailing_metres(included, order) or 0
    objective = _reported_objective(foundations, vessel, active, included, distance, order, metres)
    return "FEASIBLE", objective, order, _relaxation_bound(included, active, matrix)


def _reoptimize_window(
    included: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    distance: ConstraintInput,
    order: list[str],
    start: int,
    end: int,
    matrix: list[list[int]],
    time_limit: float,
) -> list[str]:
    builder = _Builder(
        included,
        replace(vessel, solver_time_limit_seconds=max(1, int(time_limit))),
        constraints=active,
    )
    builder.vessel = replace(builder.vessel, solver_time_limit_seconds=time_limit)
    for constraint in active:
        if constraint.constraint_type == "minimise_within_trip_distance":
            builder.add_window_distance(constraint, order, start, end, matrix)
        else:
            builder.add_constraint(constraint)
    builder.fix_outside(order, start, end)
    builder.hint(order)
    _status, _objective, candidate = builder.solve()
    if not candidate or candidate == order:
        return order
    from apps.optimisation.services.evaluation import evaluate

    if evaluate(included, vessel, active, candidate).validation_status != "Passed":
        return order
    return candidate


def _greedy_route(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    included: list[FoundationInput],
) -> list[str]:
    """Nearest feasible foundation at each position. Discarded when a hard rule fails."""
    if len(included) < 2:
        return [item.foundation_id for item in included]
    from apps.optimisation.services.between_trips import _position_checks
    from apps.optimisation.services.evaluation import evaluate

    checks = _position_checks(foundations, vessel, active)
    quotas = []
    for constraint in active:
        if (
            constraint.enforcement != "hard"
            or constraint.constraint_type != "maximum_matching_per_trip"
        ):
            continue
        matched = {
            item.foundation_id for item in matching_foundations(included, constraint.parameters)
        }
        quotas.append((matched, int(constraint.parameters["maximum_count"])))
    capacity = max(vessel.max_foundations_per_trip, 1)
    remaining = set(range(len(included)))
    order: list[str] = []
    counts: dict[int, dict[int, int]] = {index: {} for index in range(len(quotas))}
    previous: FoundationInput | None = None
    for slot in range(len(included)):
        position = slot + 1
        trip = slot // capacity + 1
        best: tuple[int, int] | None = None
        for index in remaining:
            item = included[index]
            if any(not check(item.foundation_id, position, trip) for check in checks):
                continue
            blocked = False
            for quota_index, (matched, maximum) in enumerate(quotas):
                if item.foundation_id not in matched:
                    continue
                if counts[quota_index].get(trip, 0) >= maximum:
                    blocked = True
                    break
            if blocked:
                continue
            distance = 0 if previous is None else metres_between(previous, item)
            choice = (distance, index)
            if best is None or choice < best:
                best = choice
        if best is None:
            return []
        chosen = included[best[1]]
        order.append(chosen.foundation_id)
        remaining.remove(best[1])
        for quota_index, (matched, _maximum) in enumerate(quotas):
            if chosen.foundation_id in matched:
                counts[quota_index][trip] = counts[quota_index].get(trip, 0) + 1
        previous = chosen
    if evaluate(foundations, vessel, active, order).validation_status != "Passed":
        return []
    return order


def _shorter_order(
    included: list[FoundationInput], first: list[str], second: list[str]
) -> list[str]:
    first_metres = _sailing_metres(included, first) if first else None
    second_metres = _sailing_metres(included, second) if second else None
    if second_metres is None:
        return list(first)
    if first_metres is None or second_metres < first_metres:
        return list(second)
    return list(first)


def _reported_objective(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    included: list[FoundationInput],
    distance: ConstraintInput,
    order: list[str],
    metres: int,
) -> int:
    from apps.optimisation.services.evaluation import evaluate
    from apps.optimisation.services.scaling import scaled_penalty

    review = evaluate(foundations, vessel, active, order)
    if distance.enforcement == "hard":
        return metres + review.objective_penalty
    upper = _leg_upper(included)
    span = max(upper * max(len(included) - 1, 1), 1)
    return review.objective_penalty + scaled_penalty(metres, span, distance.severity or 0)


def _relaxation_bound(
    included: list[FoundationInput], active: list[ConstraintInput], matrix: list[list[int]]
) -> int:
    """A relaxation of the full sailing path. It is not a feasible sequence."""
    indexes = list(range(len(included)))
    bound = _mst(indexes, matrix)
    prefixes = [
        item
        for item in active
        if item.enforcement == "hard" and item.constraint_type == "matching_installed_first"
    ]
    if len(prefixes) != 1:
        return bound
    names = {row.foundation_id for row in matching_foundations(included, prefixes[0].parameters)}
    matched = [index for index, item in enumerate(included) if item.foundation_id in names]
    if not 2 <= len(matched) <= 16 or len(matched) >= len(included):
        return bound
    outside = [index for index in indexes if index not in set(matched)]
    best = _prefix_path_bound(matched, outside, matrix)
    if best is None:
        return bound
    return max(bound, best)


def _prefix_path_bound(
    matched: list[int], outside: list[int], matrix: list[list[int]]
) -> int | None:
    count = len(matched)
    full = (1 << count) - 1
    inf = 10**18
    cost = [[inf] * count for _ in range(full + 1)]
    for index in range(count):
        cost[1 << index][index] = 0
    for mask in range(full + 1):
        for end in range(count):
            current = cost[mask][end]
            if current >= inf:
                continue
            for nxt in range(count):
                if mask & (1 << nxt):
                    continue
                candidate = current + matrix[matched[end]][matched[nxt]]
                nxt_mask = mask | (1 << nxt)
                if candidate < cost[nxt_mask][nxt]:
                    cost[nxt_mask][nxt] = candidate
    rest = _mst(outside, matrix)
    best: int | None = None
    for end in range(count):
        if cost[full][end] >= inf:
            continue
        if outside:
            link = min(matrix[matched[end]][other] for other in outside)
        else:
            link = 0
        total = cost[full][end] + link + rest
        if best is None or total < best:
            best = total
    return best


def _mst(indexes: list[int], matrix: list[list[int]]) -> int:
    if len(indexes) <= 1:
        return 0
    chosen = {indexes[0]}
    pending = set(indexes[1:])
    total = 0
    while pending:
        best_node = None
        best_distance = None
        for left in chosen:
            for right in pending:
                distance = matrix[left][right]
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_node = right
        if best_node is None or best_distance is None:
            break
        chosen.add(best_node)
        pending.remove(best_node)
        total += best_distance
    return total


def _distance_message(
    status: str,
    constraints: list[ConstraintInput],
    included: list[FoundationInput],
    vessel: VesselConfig,
    order: list[str],
    bound: int,
) -> str:
    message = _status_message(status, constraints)
    metres = _sailing_metres(included, order)
    if metres is None:
        return message
    within, links = _split_sailing(included, order, vessel.max_foundations_per_trip)
    from apps.optimisation.services.routing import format_nautical_miles

    gap = ""
    if metres > 0 and bound > 0:
        gap = f" Relaxed lower bound {bound} m. Gap {(metres - bound) / metres:.1%}."
    return (
        f"{message} Total sailing {format_nautical_miles(metres)} ({metres} m). "
        f"Within trips {within} m. Trip to trip {links} m.{gap}"
    )


def _longest_leg_windows(
    order: list[str],
    included: list[FoundationInput],
    matrix: list[list[int]],
    capacity: int,
) -> list[tuple[int, int]]:
    """Windows centred on the longest legs, wide enough to cross a trip boundary."""
    by_id = {item.foundation_id: index for index, item in enumerate(included)}
    legs = []
    for position in range(len(order) - 1):
        distance = matrix[by_id[order[position]]][by_id[order[position + 1]]]
        legs.append((distance, position))
    legs.sort(reverse=True)
    width = min(len(order), max(capacity * 3, 2))
    windows = []
    for _distance, position in legs[:6]:
        left = max(0, position - width // 2)
        if left + width > len(order):
            left = max(0, len(order) - width)
        windows.append((left, width))
    return windows


def _split_sailing(
    included: list[FoundationInput], order: list[str], capacity: int
) -> tuple[int, int]:
    by_id = {item.foundation_id: item for item in included}
    within = 0
    links = 0
    step = max(capacity, 1)
    for start in range(0, len(order), step):
        group = order[start : start + step]
        for left, right in zip(group, group[1:], strict=False):
            within += metres_between(by_id[left], by_id[right])
        if start + step < len(order) and group:
            links += metres_between(by_id[group[-1]], by_id[order[start + step]])
    return within, links


def _shorter_sailing(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    active: list[ConstraintInput],
    included: list[FoundationInput],
    hint: list[str],
    status: str,
    objective: int | None,
    order: list[str],
) -> tuple[str, int | None, list[str]]:
    """Keep the feasible route with the shorter full sailing distance."""
    if not hint or hint == order or len(included) <= 12:
        return status, objective, order
    from apps.optimisation.services.evaluation import evaluate
    from apps.optimisation.services.scaling import scaled_penalty

    review = evaluate(foundations, vessel, active, hint)
    if review.validation_status != "Passed":
        return status, objective, order
    hint_metres = _sailing_metres(included, hint)
    order_metres = _sailing_metres(included, order) if order else None
    if hint_metres is None or (order_metres is not None and hint_metres >= order_metres):
        return status, objective, order
    distance = next(
        item for item in active if item.constraint_type == "minimise_within_trip_distance"
    )
    if distance.enforcement == "hard":
        hint_objective = hint_metres + review.objective_penalty
    else:
        upper = _leg_upper(included)
        span = max(upper * max(len(included) - 1, 1), 1)
        hint_objective = review.objective_penalty + scaled_penalty(
            hint_metres, span, distance.severity or 0
        )
    return "FEASIBLE", hint_objective, hint


def _sailing_metres(included: list[FoundationInput], order: list[str]) -> int | None:
    if len(order) != len(included):
        return None
    by_id = {item.foundation_id: item for item in included}
    if any(name not in by_id for name in order):
        return None
    points = [by_id[name] for name in order]
    return sum(metres_between(left, right) for left, right in zip(points, points[1:], strict=False))


def _leg_upper(included: list[FoundationInput]) -> int:
    if len(included) < 2:
        return 0
    return max(
        metres_between(left, right)
        for left in included
        for right in included
        if left.foundation_id != right.foundation_id
    )


def _status_message(status: str, constraints: list[ConstraintInput]) -> str:
    if status == "INFEASIBLE":
        names = [item.name for item in constraints if item.enforcement == "hard"]
        listed = ", ".join(names) if names else "the trip structure"
        return (
            "No feasible sequence exists for the active hard constraints. "
            "No constraint was relaxed and no sequence was created. "
            f"Active hard constraints: {listed}."
        )
    if status == "UNKNOWN":
        return (
            "The solver stopped before proving a result. No sequence was created. "
            "Increase the solver time limit or simplify the constraint set. "
            "No hard constraint was relaxed."
        )
    if status == "ERROR":
        return "The solver model could not be solved. No sequence was created."
    if status == "OPTIMAL":
        return "OR-Tools reported an optimal solution for the scaled objective."
    if status == "FEASIBLE":
        return "OR-Tools reported a feasible solution before the time limit. It is not labelled optimal."
    return "The solver did not return a sequence."


class _Builder:
    def __init__(
        self,
        included: list[FoundationInput],
        vessel: VesselConfig,
        *,
        model: cp_model.CpModel | None = None,
        name_prefix: str = "",
        constraints: list | None = None,
    ) -> None:
        self.included = included
        self.vessel = vessel
        self.constraints = list(constraints or [])
        self.name_prefix = name_prefix
        self.n = len(included)
        self.capacity = vessel.max_foundations_per_trip
        self.trips = required_trips(self.n, self.capacity)
        self.model = model if model is not None else cp_model.CpModel()
        self.index = {item.foundation_id: position for position, item in enumerate(included)}
        self.kilograms = [
            weight_kg(item.weight_t) if item.weight_t is not None else 0 for item in included
        ]
        self.total_kg = sum(self.kilograms)
        self._sequence = 0
        self.objective_terms: list[Any] = []
        self.hard_distance_terms: list[Any] = []
        self.x = [
            [
                self.model.NewBoolVar(self._var(f"x_{foundation}_{position}"))
                for position in range(self.n)
            ]
            for foundation in range(self.n)
        ]
        self.position_of = [
            self.model.NewIntVar(1, max(self.n, 1), self._var(f"pos_{index}"))
            for index in range(self.n)
        ]
        self.trip_of = [
            self.model.NewIntVar(1, max(self.trips, 1), self._var(f"trip_{index}"))
            for index in range(self.n)
        ]
        self._add_assignment()

    def _var(self, name: str) -> str:
        if not self.name_prefix:
            return name
        return f"{self.name_prefix}_{name}"

    def _name(self, prefix: str) -> str:
        self._sequence += 1
        return self._var(f"{prefix}_{self._sequence}")

    def _int(self, lower: int, upper: int, prefix: str) -> Any:
        return self.model.NewIntVar(lower, max(lower, upper), self._name(prefix))

    def _bool(self, prefix: str) -> Any:
        return self.model.NewBoolVar(self._name(prefix))

    def _add_assignment(self) -> None:
        if self.n == 0:
            return
        for foundation in range(self.n):
            self.model.Add(sum(self.x[foundation][position] for position in range(self.n)) == 1)
            self.model.Add(
                self.position_of[foundation]
                == sum((position + 1) * self.x[foundation][position] for position in range(self.n))
            )
        for position in range(self.n):
            self.model.Add(sum(self.x[foundation][position] for foundation in range(self.n)) == 1)
        for foundation in range(self.n):
            terms = []
            for trip in range(1, self.trips + 1):
                positions = [
                    item - 1 for item in sequence_positions_for_trip(trip, self.n, self.capacity)
                ]
                terms.append(trip * sum(self.x[foundation][position] for position in positions))
            self.model.Add(self.trip_of[foundation] == sum(terms))

    def _trip_positions(self, trip: int) -> list[int]:
        return [item - 1 for item in sequence_positions_for_trip(trip, self.n, self.capacity)]

    def add_constraint(self, constraint: ConstraintInput) -> None:
        kind = constraint.constraint_type
        handler = {
            "maximum_trip_payload": self._payload,
            "fixed_trip": self._fixed_trip,
            "fixed_vessel_position": self._fixed_position,
            "allowed_positions": self._allowed_positions,
            "excluded_positions": self._excluded_positions,
            "earliest_sequence": self._sequence_bound,
            "latest_sequence": self._sequence_bound,
            "precedence": self._precedence,
            "maximum_matching_per_trip": self._maximum_count,
            "minimum_matching_per_trip": self._minimum_count,
            "same_trip": self._same_trip,
            "separate_trip": self._separate_trip,
            "attribute_ordering": self._ordering,
            "delivery_sequence_alignment": self._delivery,
            "difficulty_progression": self._difficulty,
            "minimise_within_trip_distance": self._distance,
            "matching_installed_first": self._installed_first,
            "avoid_matching_in_first_trips": self._avoid_first_trips,
            "loop_id_sequence": self._loop_sequence,
            "string_id_sequence": self._string_sequence,
        }.get(kind)
        if handler:
            handler(constraint)

    def add_within_trip_start(self, constraint: ConstraintInput) -> None:
        """Seed the search with a short route inside trips. The objective stays the full path."""
        if self.n < 2:
            return
        matrix = [
            [metres_between(self.included[left], self.included[right]) for right in range(self.n)]
            for left in range(self.n)
        ]
        leg_upper = max(max(row) for row in matrix)
        if leg_upper == 0:
            return
        legs: list[Any] = []
        for trip in range(1, self.trips + 1):
            positions = self._trip_positions(trip)
            for left, right in zip(positions, positions[1:], strict=False):
                legs.append(self._pair_metres(left, right, matrix, leg_upper))
        if not legs:
            return
        total = sum(legs)
        if constraint.enforcement == "hard":
            self.hard_distance_terms.append(total)
            return
        self._penalise(total, leg_upper * len(legs), constraint.severity)

    def _penalise(self, raw: Any, max_raw: int, severity: int | None) -> None:
        if not severity or max_raw <= 0:
            return
        scaled = self._int(0, severity * NORM, "penalty")
        self.model.Add(scaled * max_raw >= raw * severity * NORM)
        self.objective_terms.append(scaled)

    def _miss(self, satisfied: Any) -> Any:
        missed = self._int(0, 1, "miss")
        self.model.Add(missed == 1 - satisfied)
        return missed

    def _payload(self, constraint: ConstraintInput) -> None:
        limit = weight_kg(Decimal(str(constraint.parameters["maximum_payload_t"])))
        excesses = []
        for trip in range(1, self.trips + 1):
            positions = self._trip_positions(trip)
            weight = sum(
                self.kilograms[foundation] * self.x[foundation][position]
                for foundation in range(self.n)
                for position in positions
            )
            if constraint.enforcement == "hard":
                self.model.Add(weight <= limit)
            else:
                excess = self._int(0, max(self.total_kg, 1), "payload")
                self.model.Add(excess >= weight - limit)
                excesses.append(excess)
        if excesses:
            self._penalise(sum(excesses), max(self.total_kg, 1), constraint.severity)

    def _fixed_trip(self, constraint: ConstraintInput) -> None:
        foundation = self.index[str(constraint.parameters["foundation_id"])]
        positions = self._trip_positions(int(constraint.parameters["trip_number"]))
        placed = sum(self.x[foundation][position] for position in positions)
        if constraint.enforcement == "hard":
            self.model.Add(placed == 1)
        else:
            self._penalise(self._miss(placed), 1, constraint.severity)

    def _fixed_position(self, constraint: ConstraintInput) -> None:
        foundation = self.index[str(constraint.parameters["foundation_id"])]
        position_number = int(constraint.parameters["position_number"])
        trip_number = constraint.parameters.get("trip_number")
        if trip_number not in (None, ""):
            sequence = (int(trip_number) - 1) * self.capacity + position_number
            placed = self.x[foundation][sequence - 1]
        else:
            slots = [
                position
                for position in range(self.n)
                if (position % self.capacity) + 1 == position_number
            ]
            placed = sum(self.x[foundation][position] for position in slots)
        if constraint.enforcement == "hard":
            self.model.Add(placed == 1)
        else:
            self._penalise(self._miss(placed), 1, constraint.severity)

    def _position_rule(self, constraint: ConstraintInput, allowed: set[int]) -> None:
        slots = [
            position for position in range(self.n) if (position % self.capacity) + 1 in allowed
        ]
        matched = matching_foundations(self.included, constraint.parameters)
        misses = []
        for foundation in matched:
            index = self.index[foundation.foundation_id]
            placed = sum(self.x[index][position] for position in slots) if slots else 0
            if constraint.enforcement == "hard":
                self.model.Add(placed == 1)
            else:
                misses.append(self._miss(placed))
        if misses:
            self._penalise(sum(misses), len(misses), constraint.severity)

    def _allowed_positions(self, constraint: ConstraintInput) -> None:
        self._position_rule(
            constraint, {int(item) for item in constraint.parameters["allowed_positions"]}
        )

    def _excluded_positions(self, constraint: ConstraintInput) -> None:
        excluded = {int(item) for item in constraint.parameters["excluded_positions"]}
        allowed = set(range(1, self.capacity + 1)) - excluded
        self._position_rule(constraint, allowed)

    def _sequence_bound(self, constraint: ConstraintInput) -> None:
        earliest = constraint.constraint_type == "earliest_sequence"
        bound = _sequence_bound_value(
            constraint.parameters, constraint.constraint_type, self.capacity
        )
        matched = _bound_targets(self.included, constraint.parameters)
        pieces = []
        for foundation in matched:
            index = self.index[foundation.foundation_id]
            if constraint.enforcement == "hard":
                if earliest:
                    self.model.Add(self.position_of[index] >= bound)
                else:
                    self.model.Add(self.position_of[index] <= bound)
            else:
                short = self._int(0, max(self.n, bound), "window")
                if earliest:
                    self.model.Add(short >= bound - self.position_of[index])
                else:
                    self.model.Add(short >= self.position_of[index] - bound)
                pieces.append(short)
        if pieces:
            self._penalise(sum(pieces), max(self.n, bound) * len(pieces), constraint.severity)

    def _precedence(self, constraint: ConstraintInput) -> None:
        predecessor = self.index[str(constraint.parameters["predecessor_foundation_id"])]
        successor = self.index[str(constraint.parameters["successor_foundation_id"])]
        minimum_gap = int(constraint.parameters["minimum_gap"])
        maximum_gap = constraint.parameters.get("maximum_gap")
        gap = self.position_of[successor] - self.position_of[predecessor]
        if constraint.enforcement == "hard":
            self.model.Add(gap >= minimum_gap)
            if maximum_gap not in (None, ""):
                self.model.Add(gap <= int(maximum_gap))
            return
        short = self._int(0, self.n + minimum_gap, "gap")
        self.model.Add(short >= minimum_gap - gap)
        raw = short
        max_raw = self.n + minimum_gap
        if maximum_gap not in (None, ""):
            over = self._int(0, self.n, "gap_over")
            self.model.Add(over >= gap - int(maximum_gap))
            raw = short + over
            max_raw += self.n
        self._penalise(raw, max_raw, constraint.severity)

    def _count_expr(self, indexes: list[int], trip: int) -> Any:
        positions = self._trip_positions(trip)
        return sum(self.x[index][position] for index in indexes for position in positions)

    def _maximum_count(self, constraint: ConstraintInput) -> None:
        maximum = int(constraint.parameters["maximum_count"])
        indexes = [
            self.index[item.foundation_id]
            for item in matching_foundations(self.included, constraint.parameters)
        ]
        excesses = []
        for trip in range(1, self.trips + 1):
            count = self._count_expr(indexes, trip)
            if constraint.enforcement == "hard":
                self.model.Add(count <= maximum)
            else:
                excess = self._int(0, max(len(indexes), 1), "count")
                self.model.Add(excess >= count - maximum)
                excesses.append(excess)
        if excesses:
            self._penalise(sum(excesses), max(len(indexes), 1), constraint.severity)

    def _minimum_count(self, constraint: ConstraintInput) -> None:
        minimum = int(constraint.parameters["minimum_count"])
        applicable = constraint.parameters.get("applicable_trips") or list(range(1, self.trips + 1))
        indexes = [
            self.index[item.foundation_id]
            for item in matching_foundations(self.included, constraint.parameters)
        ]
        shorts = []
        for trip in applicable:
            count = self._count_expr(indexes, int(trip))
            if constraint.enforcement == "hard":
                self.model.Add(count >= minimum)
            else:
                short = self._int(0, minimum, "short")
                self.model.Add(short >= minimum - count)
                shorts.append(short)
        if shorts:
            self._penalise(sum(shorts), minimum * len(shorts), constraint.severity)

    def _same_trip(self, constraint: ConstraintInput) -> None:
        indexes = [self.index[str(item)] for item in constraint.parameters["foundation_ids"]]
        if constraint.enforcement == "hard":
            for other in indexes[1:]:
                self.model.Add(self.trip_of[indexes[0]] == self.trip_of[other])
            return
        mismatches = []
        for left in range(len(indexes)):
            for right in range(left + 1, len(indexes)):
                different = self._bool("split")
                self.model.Add(
                    self.trip_of[indexes[left]] != self.trip_of[indexes[right]]
                ).OnlyEnforceIf(different)
                self.model.Add(
                    self.trip_of[indexes[left]] == self.trip_of[indexes[right]]
                ).OnlyEnforceIf(different.Not())
                mismatches.append(different)
        if mismatches:
            self._penalise(sum(mismatches), len(mismatches), constraint.severity)

    def _separate_trip(self, constraint: ConstraintInput) -> None:
        indexes = [self.index[str(item)] for item in constraint.parameters["foundation_ids"]]
        shares = []
        for left in range(len(indexes)):
            for right in range(left + 1, len(indexes)):
                if constraint.enforcement == "hard":
                    self.model.Add(self.trip_of[indexes[left]] != self.trip_of[indexes[right]])
                else:
                    same = self._bool("share")
                    self.model.Add(
                        self.trip_of[indexes[left]] == self.trip_of[indexes[right]]
                    ).OnlyEnforceIf(same)
                    self.model.Add(
                        self.trip_of[indexes[left]] != self.trip_of[indexes[right]]
                    ).OnlyEnforceIf(same.Not())
                    shares.append(same)
        if shares:
            self._penalise(sum(shares), len(shares), constraint.severity)

    def _ordering(self, constraint: ConstraintInput) -> None:
        attribute = str(constraint.parameters["attribute"])
        direction = str(constraint.parameters["direction"])
        scope = str(constraint.parameters.get("scope") or constraint.scope or "full_sequence")
        if scope == "full_sequence":
            self._full_order(constraint, attribute, direction)
        else:
            self._window_order(
                constraint,
                attribute,
                direction,
                [
                    position
                    for trip in range(1, self.trips + 1)
                    for position in sequence_positions_for_trip(trip, self.n, self.capacity)
                ],
                per_trip=True,
            )

    def _difficulty(self, constraint: ConstraintInput) -> None:
        attribute = str(constraint.parameters.get("attribute") or "Difficulty_Value")
        direction = str(constraint.parameters["direction"])
        start = int(constraint.parameters["applicable_start_trip"])
        end = int(constraint.parameters["applicable_end_trip"])
        positions = positions_in_trip_window(start, end, self.n, self.capacity)
        self._window_order(constraint, attribute, direction, positions, per_trip=False)

    def _full_order(self, constraint: ConstraintInput, attribute: str, direction: str) -> None:
        pairs = ordering_pairs(self.included, attribute, direction)
        if constraint.enforcement == "hard":
            for earlier, later in pairs:
                self.model.Add(self.position_of[earlier] < self.position_of[later])
            return
        inversions = []
        for earlier, later in pairs:
            inverted = self._bool("inv")
            self.model.Add(self.position_of[earlier] > self.position_of[later]).OnlyEnforceIf(
                inverted
            )
            self.model.Add(self.position_of[earlier] < self.position_of[later]).OnlyEnforceIf(
                inverted.Not()
            )
            inversions.append(inverted)
        if inversions:
            self._penalise(sum(inversions), len(inversions), constraint.severity)

    def _window_order(
        self,
        constraint: ConstraintInput,
        attribute: str,
        direction: str,
        positions: list[int],
        *,
        per_trip: bool,
    ) -> None:
        values = attribute_values(self.included, attribute)
        span = attribute_span(values)
        groups = (
            [
                sequence_positions_for_trip(trip, self.n, self.capacity)
                for trip in range(1, self.trips + 1)
            ]
            if per_trip
            else [positions]
        )
        violations = []
        pair_count = 0
        for group in groups:
            pair_count += window_pair_count(group)
            for index, earlier in enumerate(group):
                for later in group[index + 1 :]:
                    left = sum(
                        values[foundation] * self.x[foundation][earlier - 1]
                        for foundation in range(self.n)
                    )
                    right = sum(
                        values[foundation] * self.x[foundation][later - 1]
                        for foundation in range(self.n)
                    )
                    if constraint.enforcement == "hard":
                        self.model.Add(left <= right if direction == "ascending" else left >= right)
                    elif span:
                        violation = self._int(0, span, "order")
                        self.model.Add(
                            violation
                            >= (left - right if direction == "ascending" else right - left)
                        )
                        violations.append(violation)
        if violations:
            self._penalise(sum(violations), max(span * pair_count, 1), constraint.severity)

    def _delivery(self, constraint: ConstraintInput) -> None:
        tolerance = int(constraint.parameters["tolerance_positions"])
        max_raw = delivery_max_raw(
            [item.delivery_sequence or 1 for item in self.included],
            tolerance,
        )
        excesses = []
        for index, foundation in enumerate(self.included):
            delivery = foundation.delivery_sequence or 1
            deviation = self._int(0, max(self.n, delivery), "dev")
            self.model.AddAbsEquality(deviation, self.position_of[index] - delivery)
            excess = self._int(0, max(self.n, delivery), "align")
            self.model.Add(excess >= deviation - tolerance)
            if constraint.enforcement == "hard":
                self.model.Add(excess == 0)
            else:
                excesses.append(excess)
        if excesses and max_raw > 0:
            self._penalise(sum(excesses), max_raw, constraint.severity)

    def _installed_first(self, constraint: ConstraintInput) -> None:
        indexes = [
            self.index[item.foundation_id]
            for item in matching_foundations(self.included, constraint.parameters)
        ]
        count = len(indexes)
        if count == 0:
            return
        if constraint.enforcement == "hard":
            for index in indexes:
                self.model.Add(self.position_of[index] <= count)
            return
        violations = []
        for index in indexes:
            over = self._int(0, self.n, "late_group")
            self.model.Add(over >= self.position_of[index] - count)
            violations.append(over)
        self._penalise(sum(violations), max(count * self.n, 1), constraint.severity)

    def _avoid_first_trips(self, constraint: ConstraintInput) -> None:
        trip_count = int(constraint.parameters["trip_count"])
        earliest = trip_count * self.capacity + 1
        indexes = [
            self.index[item.foundation_id]
            for item in matching_foundations(self.included, constraint.parameters)
        ]
        if not indexes:
            return
        if constraint.enforcement == "hard":
            for index in indexes:
                self.model.Add(self.position_of[index] >= earliest)
            return
        limit = max(earliest - 1, 1)
        violations = []
        for index in indexes:
            short = self._int(0, limit, "early_trip")
            self.model.Add(short >= earliest - self.position_of[index])
            violations.append(short)
        self._penalise(sum(violations), max(limit * len(indexes), 1), constraint.severity)

    def _loop_sequence(self, constraint: ConstraintInput) -> None:
        self._ordered_blocks(loop_blocks(self.included, self.constraints), constraint, "loop")

    def _string_sequence(self, constraint: ConstraintInput) -> None:
        self._ordered_blocks(string_blocks(self.included, self.constraints), constraint, "string")

    def _ordered_blocks(self, groups: list[list[int]], constraint: ConstraintInput, prefix: str) -> None:
        if not groups or self.n < 2:
            return
        if constraint.enforcement == "hard":
            for indexes in groups:
                for left, right in zip(indexes, indexes[1:], strict=False):
                    self.model.Add(self.position_of[right] == self.position_of[left] + 1)
                    self.model.Add(self.trip_of[right] == self.trip_of[left])
            return
        terms = []
        span = (self.n - 1) + self.n
        for indexes in groups:
            for left, right in zip(indexes, indexes[1:], strict=False):
                gap = self._int(1 - self.n, self.n - 1, f"{prefix}gap")
                self.model.Add(gap == self.position_of[right] - self.position_of[left] - 1)
                deviation = self._int(0, self.n - 1, f"{prefix}dev")
                self.model.AddAbsEquality(deviation, gap)
                same_trip = self._bool(f"{prefix}same")
                self.model.Add(self.trip_of[right] == self.trip_of[left]).OnlyEnforceIf(same_trip)
                self.model.Add(self.trip_of[right] != self.trip_of[left]).OnlyEnforceIf(
                    same_trip.Not()
                )
                terms.append(deviation + (1 - same_trip) * self.n)
        if terms:
            self._penalise(sum(terms), span * len(terms), constraint.severity)

    def _distance(self, constraint: ConstraintInput) -> None:
        """Minimise every consecutive foundation-to-foundation leg. Harbour is excluded."""
        if self.n < 2:
            return
        matrix = [
            [metres_between(self.included[left], self.included[right]) for right in range(self.n)]
            for left in range(self.n)
        ]
        leg_upper = max(max(row) for row in matrix)
        if leg_upper == 0:
            return
        legs = [
            self._pair_metres(position, position + 1, matrix, leg_upper)
            for position in range(self.n - 1)
        ]
        total = sum(legs)
        if constraint.enforcement == "hard":
            self.hard_distance_terms.append(total)
            return
        self._penalise(total, leg_upper * (self.n - 1), constraint.severity)

    def _pair_metres(self, left: int, right: int, matrix: list[list[int]], upper: int) -> Any:
        # One origin occupies `left` and one destination occupies `right`.
        # Minimising this variable makes it equal to that pair's metres.
        cost = self._int(0, upper, "leg")
        for origin in range(self.n):
            for destination in range(self.n):
                distance = matrix[origin][destination]
                if distance <= 0 or origin == destination:
                    continue
                self.model.Add(
                    cost >= distance * (self.x[origin][left] + self.x[destination][right] - 1)
                )
        return cost

    def add_window_distance(
        self,
        constraint: ConstraintInput,
        order: list[str],
        start: int,
        end: int,
        matrix: list[list[int]],
    ) -> None:
        """Minimise the full-path legs that touch one stretch of the sequence."""
        if self.n < 2 or end - start < 2:
            return
        leg_upper = max(max(row) for row in matrix)
        if leg_upper == 0:
            return
        free = [self.index[order[position]] for position in range(start, end)]

        def side(position: int) -> list[int]:
            if start <= position < end:
                return free
            return [self.index[order[position]]]

        legs = []
        last = min(self.n - 1, end)
        for left in range(max(0, start - 1), last):
            origins = side(left)
            destinations = side(left + 1)
            if len(origins) == 1 and len(destinations) == 1:
                continue
            legs.append(
                self._pair_between(left, left + 1, origins, destinations, matrix, leg_upper)
            )
        if not legs:
            return
        total = sum(legs)
        if constraint.enforcement == "hard":
            self.hard_distance_terms.append(total)
            return
        self._penalise(total, leg_upper * (self.n - 1), constraint.severity)

    def _pair_between(
        self,
        left: int,
        right: int,
        origins: list[int],
        destinations: list[int],
        matrix: list[list[int]],
        upper: int,
    ) -> Any:
        cost = self._int(0, upper, "leg")
        for origin in origins:
            for destination in destinations:
                distance = matrix[origin][destination]
                if distance <= 0 or origin == destination:
                    continue
                self.model.Add(
                    cost >= distance * (self.x[origin][left] + self.x[destination][right] - 1)
                )
        return cost

    def fix_outside(self, order: list[str], start: int, end: int) -> None:
        for slot, name in enumerate(order):
            if start <= slot < end:
                continue
            self.model.Add(self.x[self.index[name]][slot] == 1)

    def hint(self, order: list[str]) -> None:
        positions = {name: index for index, name in enumerate(order)}
        chosen = [positions.get(item.foundation_id) for item in self.included]
        if len(order) != self.n or any(slot is None for slot in chosen):
            return
        for foundation, slot in enumerate(chosen):
            for index in range(self.n):
                self.model.AddHint(self.x[foundation][index], 1 if index == slot else 0)

    def read_order(self, solver: cp_model.CpSolver) -> list[str]:
        order = [""] * self.n
        for foundation in range(self.n):
            for position in range(self.n):
                if solver.Value(self.x[foundation][position]):
                    order[position] = self.included[foundation].foundation_id
        return order

    def solve(self) -> tuple[str, int | None, list[str]]:
        if self.n == 0:
            return "ERROR", None, []
        terms = _combined_objective([self])
        has_objective = bool(terms)
        if has_objective:
            self.model.Minimize(sum(terms))
        solver = _solver(self.vessel.solver_time_limit_seconds)
        status = _run_solver(solver, self.model)
        if status not in {"OPTIMAL", "FEASIBLE"}:
            return status, None, []
        order = self.read_order(solver)
        if any(item == "" for item in order):
            return "ERROR", None, []
        objective = int(round(solver.ObjectiveValue())) if has_objective else 0
        return status, objective, order


def _sequence_bound_value(parameters: dict[str, Any], kind: str, capacity: int) -> int:
    sequence_key = "earliest_sequence" if kind == "earliest_sequence" else "latest_sequence"
    trip_key = "earliest_trip" if kind == "earliest_sequence" else "latest_trip"
    if parameters.get(sequence_key) not in (None, ""):
        return int(parameters[sequence_key])
    trip = int(parameters[trip_key])
    if kind == "earliest_sequence":
        return (trip - 1) * capacity + 1
    return trip * capacity


def _bound_targets(
    included: list[FoundationInput], parameters: dict[str, Any]
) -> list[FoundationInput]:
    if parameters.get("attribute"):
        return matching_foundations(included, parameters)
    wanted = str(parameters.get("foundation_id") or "")
    return [item for item in included if item.foundation_id == wanted]
