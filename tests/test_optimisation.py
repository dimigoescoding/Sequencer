"""CP-SAT behaviour for hard constraints, soft penalties, and infeasible models."""

import pytest
from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.services.evaluation import evaluate
from apps.optimisation.services.runner import execute
from apps.optimisation.services.scaling import scaled_penalty
from apps.optimisation.services.solver import solve_order
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from tests.support import constraint, foundation, valid_row, vessel, workbook_bytes


def test_severity_scaling_is_linear():
    assert scaled_penalty(4, 5, 100) == 2 * scaled_penalty(4, 5, 50)
    assert scaled_penalty(4, 5, 100) > scaled_penalty(4, 5, 50)


def test_included_foundations_appear_once_and_excluded_are_omitted():
    foundations = [
        foundation("A", 100, 1),
        foundation("B", 110, 2),
        foundation("C", 120, 3, include=False),
    ]
    status, _objective, _runtime, _message, order = solve_order(
        foundations, vessel(max_foundations_per_trip=2), []
    )
    assert status == "OPTIMAL"
    assert order == ["A", "B"] or sorted(order) == ["A", "B"]
    assert order.count("A") == 1
    assert "C" not in order


def test_hard_fixed_trip_position_payload_window_and_precedence():
    foundations = [
        foundation("A", 100, 1, punch_through=True),
        foundation("B", 250, 2),
        foundation("C", 250, 3),
        foundation("D", 100, 4),
    ]
    constraints = [
        constraint("A on trip 1", "fixed_trip", {"foundation_id": "A", "trip_number": 1}),
        constraint(
            "Punch positions",
            "allowed_positions",
            {
                "attribute": "Punch_Through",
                "operator": "equals",
                "value": "Yes",
                "allowed_positions": [2],
            },
        ),
        constraint("Payload", "maximum_trip_payload", {"maximum_payload_t": "400"}),
        constraint(
            "D not first", "earliest_sequence", {"foundation_id": "D", "earliest_sequence": 3}
        ),
        constraint(
            "B before C",
            "precedence",
            {"predecessor_foundation_id": "B", "successor_foundation_id": "C", "minimum_gap": 1},
        ),
    ]
    status, _objective, _runtime, _message, order = solve_order(
        foundations,
        vessel(max_foundations_per_trip=2),
        constraints,
    )
    assert status == "OPTIMAL"
    assert set(order) == {"A", "B", "C", "D"}
    assert order.index("A") // 2 + 1 == 1
    assert (order.index("A") % 2) + 1 == 2
    assert order.index("B") < order.index("C")
    assert order.index("D") + 1 >= 3
    first_trip = order[:2]
    assert not {"B", "C"} <= set(first_trip)
    second_trip = order[2:]
    assert not {"B", "C"} <= set(second_trip)
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), constraints, order)
    assert result.validation_status == "Passed"


def test_infeasible_model_returns_no_sequence():
    foundations = [foundation("A", 300), foundation("B", 300), foundation("C", 300)]
    constraints = [constraint("Payload", "maximum_trip_payload", {"maximum_payload_t": "500"})]
    status, objective, _runtime, message, order = solve_order(
        foundations,
        vessel(max_foundations_per_trip=2),
        constraints,
    )
    assert status == "INFEASIBLE"
    assert objective is None
    assert order == []
    assert "not relaxed" in message.casefold() or "No constraint was relaxed" in message


def test_soft_constraint_can_lose_and_still_report_a_penalty():
    foundations = [
        foundation("A", 10, 1),
        foundation("B", 20, 2),
        foundation("C", 30, 3),
    ]
    settings = vessel(max_foundations_per_trip=3)

    def run(weight_severity: int, delivery_severity: int):
        constraints = [
            constraint(
                "Heavy first",
                "attribute_ordering",
                {"attribute": "Weight_t", "direction": "descending", "scope": "full_sequence"},
                enforcement="soft",
                severity=weight_severity,
            ),
            constraint(
                "Delivery order",
                "delivery_sequence_alignment",
                {"tolerance_positions": 0},
                enforcement="soft",
                severity=delivery_severity,
            ),
        ]
        status, objective, _runtime, _message, order = solve_order(
            foundations, settings, constraints
        )
        reviewed = evaluate(foundations, settings, constraints, order)
        return status, objective, order, reviewed

    strong, strong_objective, strong_order, strong_review = run(100, 100)
    weaker, weaker_objective, weaker_order, weaker_review = run(50, 100)
    assert strong == "OPTIMAL"
    assert weaker == "OPTIMAL"
    assert strong_order == ["C", "B", "A"]
    assert weaker_order == ["A", "B", "C"]
    assert strong_objective == 80000
    assert weaker_objective == 50000
    assert strong_review.objective_penalty == strong_objective
    assert weaker_review.soft_tradeoff_count >= 1
    assert any(row.status == "Soft trade-off" for row in weaker_review.validation_rows)


@pytest.mark.django_db
def test_infeasible_run_is_stored_without_a_fabricated_sequence():
    user = get_user_model().objects.create_user(username="solver", password="local-pass-123")
    project = Project.objects.create(owner=user, name="Infeasible", package_type="Foundation")
    content = workbook_bytes(
        [
            valid_row("A", Weight_t=300),
            valid_row("B", Weight_t=300, Delivery_Sequence=2),
            valid_row("C", Weight_t=300, Delivery_Sequence=3),
        ]
    )
    version = create_dataset_version(
        project=project, user=user, filename="infeasible.xlsx", content=content
    )
    activate_dataset(version)
    scenario = Scenario.objects.create(project=project, name="Blocked", dataset_version=version)
    VesselSettings.objects.create(
        scenario=scenario,
        max_foundations_per_trip=2,
        allow_partial_final_trip=True,
        solver_time_limit_seconds=10,
    )
    constraint_row = Constraint.objects.create(
        scenario=scenario,
        name="Payload",
        constraint_type="maximum_trip_payload",
        enforcement="hard",
        severity=None,
        active=True,
        parameters_json={"maximum_payload_t": "500"},
        display_order=1,
    )
    run = execute(scenario)
    constraint_row.refresh_from_db()
    assert run.status == "INFEASIBLE"
    assert run.solver_status == "INFEASIBLE"
    assert run.sequence_rows.count() == 0
    assert constraint_row.enforcement == "hard"
    assert run.constraint_snapshot[0]["enforcement"] == "hard"
