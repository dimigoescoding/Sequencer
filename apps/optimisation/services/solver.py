"""CP-SAT model for the foundation installation sequence.

The only decision is the global sequence. Trip number and vessel position are
derived from that sequence. Hard constraints are added to the model. Soft
constraints become scaled penalty terms. Hard constraints are never dropped.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from ortools.sat.python import cp_model

from apps.constraints.services.matching import matching_foundations
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
from apps.optimisation.services.routing import harbour_coordinates, metres_between, metres_xy
from apps.optimisation.services.scaling import (
    NORM,
    PRIMARY_WEIGHT,
    SOLVER_SEED,
    weight_kg,
)
from apps.optimisation.services.types import ConstraintInput, FoundationInput, VesselConfig


def solve_order(
    foundations: list[FoundationInput],
    vessel: VesselConfig,
    constraints: list[ConstraintInput],
) -> tuple[str, int | None, float, str, list[str]]:
    included = [item for item in foundations if item.include]
    active = [item for item in constraints if item.active]
    builder = _Builder(included, vessel)
    for constraint in active:
        builder.add_constraint(constraint)
    started = time.perf_counter()
    status, objective, order = builder.solve()
    runtime = time.perf_counter() - started
    message = _status_message(status, active)
    return status, objective, runtime, message, order


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
    def __init__(self, included: list[FoundationInput], vessel: VesselConfig) -> None:
        self.included = included
        self.vessel = vessel
        self.n = len(included)
        self.capacity = vessel.max_foundations_per_trip
        self.trips = required_trips(self.n, self.capacity)
        self.model = cp_model.CpModel()
        self.index = {item.foundation_id: position for position, item in enumerate(included)}
        self.kilograms = [
            weight_kg(item.weight_t) if item.weight_t is not None else 0 for item in included
        ]
        self.total_kg = sum(self.kilograms)
        self._sequence = 0
        self.objective_terms: list[Any] = []
        self.x = [
            [self.model.NewBoolVar(f"x_{foundation}_{position}") for position in range(self.n)]
            for foundation in range(self.n)
        ]
        self.position_of = [
            self.model.NewIntVar(1, max(self.n, 1), f"pos_{index}") for index in range(self.n)
        ]
        self.trip_of = [
            self.model.NewIntVar(1, max(self.trips, 1), f"trip_{index}") for index in range(self.n)
        ]
        self._add_assignment()

    def _name(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}_{self._sequence}"

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
        }.get(kind)
        if handler:
            handler(constraint)

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

    def _distance(self, constraint: ConstraintInput) -> None:
        matrix = [
            [metres_between(left, right) if left is not right else 0 for right in self.included]
            for left in self.included
        ]
        max_pair = max((max(row) for row in matrix), default=0)
        legs: list[Any] = []
        leg_count = 0
        for position in range(self.n - 1):
            if position // self.capacity != (position + 1) // self.capacity:
                continue
            leg_count += 1
            terms = []
            for left in range(self.n):
                for right in range(self.n):
                    if left == right or matrix[left][right] == 0:
                        continue
                    both = self._bool("leg")
                    self.model.AddMultiplicationEquality(
                        both, [self.x[left][position], self.x[right][position + 1]]
                    )
                    terms.append(matrix[left][right] * both)
            if terms:
                legs.append(sum(terms))
        harbour = harbour_coordinates(constraint.parameters, self.vessel)
        harbour_max = 0
        if harbour is not None:
            easting, northing = harbour
            harbour_distance = [
                metres_xy(item.easting_m, item.northing_m, easting, northing)
                for item in self.included
            ]
            harbour_max = max(harbour_distance, default=0)
            for trip in range(1, self.trips + 1):
                positions = self._trip_positions(trip)
                if not positions:
                    continue
                legs.append(
                    sum(
                        harbour_distance[index] * self.x[index][positions[0]]
                        for index in range(self.n)
                    )
                )
                legs.append(
                    sum(
                        harbour_distance[index] * self.x[index][positions[-1]]
                        for index in range(self.n)
                    )
                )
        if not legs:
            return
        raw = sum(legs)
        if constraint.enforcement == "hard":
            self.objective_terms.append(PRIMARY_WEIGHT * raw)
            return
        max_raw = max_pair * max(leg_count, 1) + harbour_max * 2 * max(self.trips, 1)
        self._penalise(raw, max(max_raw, 1), constraint.severity)

    def solve(self) -> tuple[str, int | None, list[str]]:
        if self.n == 0:
            return "ERROR", None, []
        if self.objective_terms:
            self.model.Minimize(sum(self.objective_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(self.vessel.solver_time_limit_seconds)
        solver.parameters.random_seed = SOLVER_SEED
        solver.parameters.num_search_workers = 1
        code = solver.Solve(self.model)
        status = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.UNKNOWN: "UNKNOWN",
            cp_model.MODEL_INVALID: "ERROR",
        }.get(code, "ERROR")
        if status not in {"OPTIMAL", "FEASIBLE"}:
            return status, None, []
        order = [""] * self.n
        for foundation in range(self.n):
            for position in range(self.n):
                if solver.Value(self.x[foundation][position]):
                    order[position] = self.included[foundation].foundation_id
        if any(item == "" for item in order):
            return "ERROR", None, []
        objective = int(round(solver.ObjectiveValue())) if self.objective_terms else 0
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
