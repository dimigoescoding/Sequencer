"""Run CP-SAT for one scenario and store the independent validation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.constraints.models import Constraint
from apps.datasets.services.mapping import to_foundation_input
from apps.optimisation.models import OptimisationRun, SequenceResult, TripResult, ValidationResult
from apps.optimisation.services.conflicts import find_conflicts
from apps.optimisation.services.evaluation import evaluate
from apps.optimisation.services.scaling import SOLVER_SEED
from apps.optimisation.services.solver import solve_order
from apps.optimisation.services.types import ConstraintInput, ValidationRow, VesselConfig
from apps.scenarios.models import Scenario, VesselSettings


class SolveBlocked(Exception):
    def __init__(self, conflicts: list[str]) -> None:
        super().__init__("Optimisation was not started.")
        self.conflicts = conflicts


def vessel_config(settings: VesselSettings) -> VesselConfig:
    return VesselConfig(
        max_foundations_per_trip=settings.max_foundations_per_trip,
        allow_partial_final_trip=settings.allow_partial_final_trip,
        base_maximum_trip_payload_t=settings.base_maximum_trip_payload_t,
        solver_time_limit_seconds=settings.solver_time_limit_seconds,
        transit_speed_knots=settings.transit_speed_knots,
        harbour_easting_m=settings.harbour_easting_m,
        harbour_northing_m=settings.harbour_northing_m,
    )


def constraint_input(row: Constraint) -> ConstraintInput:
    return ConstraintInput(
        name=row.name,
        constraint_type=row.constraint_type,
        parameters=row.parameters_json or {},
        enforcement=row.enforcement,
        active=row.active,
        severity=row.severity,
        description=row.description,
        scope=row.scope,
        display_order=row.display_order,
        constraint_id=row.pk,
    )


def scenario_context(scenario: Scenario):
    dataset = scenario.dataset_version
    foundations = []
    columns: set[str] = set()
    if dataset is not None:
        foundations = [to_foundation_input(row) for row in dataset.foundations.all()]
        columns = set(dataset.columns_json or [])
    vessel = vessel_config(scenario.vessel_settings)
    constraints = [constraint_input(row) for row in scenario.constraints.all()]
    return foundations, vessel, constraints, columns


def blocking_messages(scenario: Scenario) -> list[str]:
    if scenario.dataset_version_id is None:
        return ["Select a dataset version before generating a sequence."]
    dataset = scenario.dataset_version
    messages: list[str] = []
    if dataset.error_count:
        messages.append(
            "The selected dataset has critical validation errors. Correct the workbook and upload a new version."
        )
    foundations, vessel, constraints, columns = scenario_context(scenario)
    if not dataset.error_count:
        messages.extend(find_conflicts(foundations, vessel, constraints, columns))
    return messages


def execute(scenario: Scenario) -> OptimisationRun:
    messages = blocking_messages(scenario)
    if messages:
        raise SolveBlocked(messages)
    foundations, vessel, constraints, _columns = scenario_context(scenario)
    active = [item for item in constraints if item.active]
    started = timezone.now()
    try:
        status, objective, runtime, message, order = solve_order(foundations, vessel, constraints)
    except Exception as exc:
        status, objective, runtime, message, order = (
            "ERROR",
            None,
            0,
            f"The solver raised an error and no sequence was created: {exc.__class__.__name__}.",
            [],
        )
    evaluation = None
    run_status = status
    if order:
        evaluation = evaluate(foundations, vessel, constraints, order)
        if evaluation.validation_status != "Passed":
            run_status = "INVALID"
            message = (
                "The solver returned a sequence that failed independent hard validation. "
                "The run is not an approved solution. No hard constraint was relaxed. " + message
            )
    return _persist(
        scenario,
        status=run_status,
        solver_status=status,
        objective=objective,
        runtime=runtime,
        message=message,
        order=order,
        evaluation=evaluation,
        active=active,
        vessel=vessel,
        constraints=constraints,
        started=started,
    )


def _persist(
    scenario,
    *,
    status,
    solver_status,
    objective,
    runtime,
    message,
    order,
    evaluation,
    active,
    vessel,
    constraints,
    started,
) -> OptimisationRun:
    # status may be INVALID after a hard-validation failure. solver_status stays
    # the value OR-Tools reported and is never rewritten as OPTIMAL.
    included_count = sum(1 for item in scenario.dataset_version.foundations.all() if item.include)
    trip_count = len(evaluation.trip_rows) if evaluation else 0
    with transaction.atomic():
        run = OptimisationRun.objects.create(
            scenario=scenario,
            dataset_version=scenario.dataset_version,
            status=status,
            solver_status=solver_status,
            validation_status=evaluation.validation_status
            if evaluation
            else OptimisationRun.ValidationStatus.NOT_RUN,
            objective_value=objective,
            runtime_seconds=runtime,
            seed=SOLVER_SEED,
            message=message,
            included_count=included_count,
            trip_count=trip_count,
            hard_constraint_count=sum(1 for item in active if item.enforcement == "hard"),
            soft_constraint_count=sum(1 for item in active if item.enforcement == "soft"),
            soft_tradeoff_count=evaluation.soft_tradeoff_count if evaluation else 0,
            vessel_snapshot=_vessel_snapshot(vessel),
            constraint_snapshot=[_constraint_snapshot(item) for item in constraints],
            started_at=started,
            finished_at=timezone.now(),
        )
        if evaluation and evaluation.sequence_rows:
            SequenceResult.objects.bulk_create(
                [
                    SequenceResult(run=run, **_sequence_kwargs(row))
                    for row in evaluation.sequence_rows
                ]
            )
            TripResult.objects.bulk_create(
                [TripResult(run=run, **_trip_kwargs(row)) for row in evaluation.trip_rows]
            )
        validation_rows = list(evaluation.validation_rows) if evaluation else []
        if not order:
            validation_rows.append(
                ValidationRow(
                    check_name="Solver result",
                    constraint_name="",
                    target="A feasible sequence",
                    actual_result=solver_status,
                    status="Information",
                    affected_foundations="",
                    explanation=message,
                    display_order=1,
                )
            )
        if validation_rows:
            ValidationResult.objects.bulk_create(
                [
                    ValidationResult(
                        run=run,
                        check_name=row.check_name,
                        constraint_name=row.constraint_name,
                        target=row.target,
                        actual_result=row.actual_result,
                        status=row.status,
                        affected_foundations=row.affected_foundations,
                        explanation=row.explanation,
                        display_order=row.display_order,
                    )
                    for row in validation_rows
                ]
            )
    return run


def _json_number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _vessel_snapshot(vessel: VesselConfig) -> dict[str, Any]:
    return {
        "max_foundations_per_trip": vessel.max_foundations_per_trip,
        "allow_partial_final_trip": vessel.allow_partial_final_trip,
        "base_maximum_trip_payload_t": _json_number(vessel.base_maximum_trip_payload_t),
        "solver_time_limit_seconds": vessel.solver_time_limit_seconds,
        "transit_speed_knots": _json_number(vessel.transit_speed_knots),
        "harbour_easting_m": _json_number(vessel.harbour_easting_m),
        "harbour_northing_m": _json_number(vessel.harbour_northing_m),
    }


def _constraint_snapshot(constraint: ConstraintInput) -> dict[str, Any]:
    return {
        "name": constraint.name,
        "constraint_type": constraint.constraint_type,
        "description": constraint.description,
        "active": constraint.active,
        "enforcement": constraint.enforcement,
        "severity": constraint.severity,
        "scope": constraint.scope,
        "display_order": constraint.display_order,
        "parameters": constraint.parameters,
    }


def _sequence_kwargs(row) -> dict[str, Any]:
    return {
        "installation_sequence": row.installation_sequence,
        "trip": row.trip,
        "vessel_position": row.vessel_position,
        "foundation_id": row.foundation_id,
        "weight_t": row.weight_t,
        "trip_total_weight_t": row.trip_total_weight_t,
        "delivery_sequence": row.delivery_sequence,
        "sequence_deviation": row.sequence_deviation,
        "delivery_batch": row.delivery_batch,
        "difficulty_value": row.difficulty_value,
        "punch_through": row.punch_through,
        "fixed_trip": row.fixed_trip,
        "fixed_position": row.fixed_position,
        "earliest_sequence": row.earliest_sequence,
        "latest_sequence": row.latest_sequence,
        "hard_constraint_status": row.hard_constraint_status,
        "soft_penalty": row.soft_penalty,
        "governing_constraints": row.governing_constraints,
        "notes": row.notes,
    }


def _trip_kwargs(row) -> dict[str, Any]:
    return {
        "trip": row.trip,
        "foundation_count": row.foundation_count,
        "foundations_in_order": row.foundations_in_order,
        "payload_limit_t": row.payload_limit_t,
        "total_weight_t": row.total_weight_t,
        "remaining_payload_t": row.remaining_payload_t,
        "punch_through_count": row.punch_through_count,
        "average_difficulty": row.average_difficulty,
        "maximum_difficulty": row.maximum_difficulty,
        "route_distance": row.route_distance,
        "payload_check": row.payload_check,
        "position_check": row.position_check,
        "overall_trip_check": row.overall_trip_check,
    }
