"""CP-SAT behaviour for hard constraints, soft penalties, and infeasible models."""

import time
from decimal import Decimal

import pytest
from apps.constraints.forms import ConstraintForm
from apps.constraints.models import Constraint
from apps.datasets.services.uploads import activate_dataset, create_dataset_version
from apps.optimisation.services.evaluation import evaluate
from apps.optimisation.services.runner import execute
from apps.optimisation.services.scaling import scaled_penalty
from apps.optimisation.services.solver import solve_order
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings
from django.contrib.auth import get_user_model
from tests.support import constraint, foundation, information_workbook, location_row, vessel


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
    content = information_workbook(
        [
            location_row("A", **{"Aver. Weight[t]": 300, "Location": 1}),
            location_row("B", **{"Aver. Weight[t]": 300, "Location": 2}),
            location_row("C", **{"Aver. Weight[t]": 300, "Location": 3}),
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


def test_spider_locations_lead_and_one_shallow_is_allowed_per_trip():
    from apps.optimisation.services.evaluation import evaluate
    from apps.optimisation.services.solver import solve_order

    foundations = [
        foundation("S1", attributes={"Spider location": True, "Shallow location": False}),
        foundation("S2", attributes={"Spider location": True, "Shallow location": False}),
        foundation("A", attributes={"Spider location": False, "Shallow location": True}),
        foundation("B", attributes={"Spider location": False, "Shallow location": True}),
        foundation("C", attributes={"Spider location": False, "Shallow location": False}),
        foundation("D", attributes={"Spider location": False, "Shallow location": False}),
    ]
    rules = [
        constraint(
            "Spider locations FOU",
            "matching_installed_first",
            {"attribute": "Spider location", "operator": "equals", "value": "YES"},
        ),
        constraint(
            "Shallow locations",
            "maximum_matching_per_trip",
            {
                "attribute": "Shallow location",
                "operator": "equals",
                "value": "YES",
                "maximum_count": 1,
            },
        ),
    ]
    limits = vessel(max_foundations_per_trip=2, solver_time_limit_seconds=10)
    status, _objective, _runtime, _message, order = solve_order(foundations, limits, rules)
    assert status == "OPTIMAL"
    assert set(order[:2]) == {"S1", "S2"}
    for trip in range(3):
        group = order[trip * 2 : trip * 2 + 2]
        assert len([name for name in group if name in {"A", "B"}]) <= 1
    review = evaluate(foundations, limits, rules, order)
    assert review.validation_status == "Passed"


def test_solver_minimises_distance_inside_one_trip():
    foundations = [
        foundation("A", easting_m=Decimal(0), northing_m=Decimal(0)),
        foundation("B", easting_m=Decimal(5), northing_m=Decimal(0)),
        foundation("C", easting_m=Decimal(1), northing_m=Decimal(0)),
    ]
    rule = constraint(
        "Infield sailing optimization FOU",
        "minimise_within_trip_distance",
        {"include_harbour_legs": False},
    )
    limits = vessel(max_foundations_per_trip=3)
    status, objective, _runtime, _message, order = solve_order(foundations, limits, [rule])
    assert status == "OPTIMAL"
    assert objective == 5
    assert _path(foundations, order) == 5
    assert order[1] == "C"
    review = evaluate(foundations, limits, [rule], order)
    assert review.validation_status == "Passed"
    assert any(
        row.check_name == "Within-trip distance" and row.status == "Information"
        for row in review.validation_rows
    )
    inactive = constraint(
        "Route",
        "minimise_within_trip_distance",
        {"include_harbour_legs": False},
        active=False,
    )
    idle_status, idle_objective, _runtime, _message, _idle_order = solve_order(
        foundations, limits, [inactive]
    )
    assert idle_status == "OPTIMAL"
    assert idle_objective == 0


def test_solver_puts_nearby_locations_on_the_same_trip():
    foundations = [
        foundation("A", easting_m=Decimal(0), northing_m=Decimal(0)),
        foundation("B", easting_m=Decimal(0), northing_m=Decimal(10)),
        foundation("C", easting_m=Decimal(100), northing_m=Decimal(0)),
        foundation("D", easting_m=Decimal(100), northing_m=Decimal(10)),
    ]
    rule = constraint(
        "Infield sailing optimization FOU",
        "minimise_within_trip_distance",
        {"include_harbour_legs": False},
    )
    limits = vessel(max_foundations_per_trip=2)
    status, objective, _runtime, _message, order = solve_order(foundations, limits, [rule])
    assert status == "OPTIMAL"
    assert objective == 20
    assert {frozenset(order[:2]), frozenset(order[2:])} == {
        frozenset({"A", "B"}),
        frozenset({"C", "D"}),
    }


def test_distance_objective_keeps_a_hard_position_rule():
    foundations = [
        foundation(
            "S4", easting_m=Decimal(0), northing_m=Decimal(0), attributes={"Spider location": True}
        ),
        foundation(
            "A", easting_m=Decimal(1), northing_m=Decimal(0), attributes={"Spider location": False}
        ),
        foundation(
            "B", easting_m=Decimal(10), northing_m=Decimal(0), attributes={"Spider location": False}
        ),
    ]
    rules = [
        constraint(
            "Spider locations FOU",
            "matching_installed_first",
            {"attribute": "Spider location", "operator": "equals", "value": "YES"},
        ),
        constraint(
            "Infield sailing optimization FOU",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
        ),
    ]
    limits = vessel(max_foundations_per_trip=3)
    status, objective, _runtime, _message, order = solve_order(foundations, limits, rules)
    assert status == "OPTIMAL"
    assert order == ["S4", "A", "B"]
    assert objective == 10
    assert evaluate(foundations, limits, rules, order).validation_status == "Passed"


def test_workbook_distance_is_the_solver_objective():
    from apps.datasets.services.parsing import parse_workbook
    from apps.optimisation.services.types import ConstraintInput

    with open("tests/fixtures/sequencer_input.xlsx", "rb") as handle:
        parsed = parse_workbook(handle.read())
    rules = [
        ConstraintInput(
            name=item.name,
            constraint_type=item.constraint_type,
            parameters=item.parameters,
            enforcement=item.enforcement,
            active=item.active,
            severity=item.severity,
            description=item.explanation,
        )
        for item in parsed.constraints
    ]
    plain = [item for item in rules if item.constraint_type != "minimise_within_trip_distance"]
    limits = vessel(max_foundations_per_trip=4, solver_time_limit_seconds=20)
    _status, _objective, _runtime, _message, baseline = solve_order(
        parsed.foundations, limits, plain
    )
    started = time.perf_counter()
    status, objective, _runtime, _message, order = solve_order(parsed.foundations, limits, rules)
    elapsed = time.perf_counter() - started
    assert status in {"OPTIMAL", "FEASIBLE"}
    assert objective is not None and objective > 0
    assert elapsed < 30
    assert len(order) == 50
    assert _within_trip_path(parsed.foundations, order, 4) < _within_trip_path(
        parsed.foundations, baseline, 4
    )
    review = evaluate(parsed.foundations, limits, rules, order)
    assert review.validation_status == "Passed"
    spiders = {
        item.foundation_id
        for item in parsed.foundations
        if item.attributes.get("Spider location") is True
    }
    assert set(order[: len(spiders)]) == spiders
    shallow = {
        item.foundation_id
        for item in parsed.foundations
        if item.attributes.get("Shallow location") is True
    }
    for start in range(0, 50, 4):
        group = order[start : start + 4]
        assert len([name for name in group if name in shallow]) <= 1


def test_earliest_trip_keeps_matching_locations_out_of_earlier_trips():
    foundations = [
        foundation("A", attributes={"Shallow location": False}),
        foundation("B", attributes={"Shallow location": True}),
        foundation("C", attributes={"Shallow location": False}),
        foundation("D", attributes={"Shallow location": True}),
    ]
    limits = vessel(max_foundations_per_trip=2)
    rules = [
        constraint(
            "No shallow first",
            "earliest_sequence",
            {
                "attribute": "Shallow location",
                "operator": "equals",
                "value": "YES",
                "earliest_trip": 2,
            },
        )
    ]
    status, _objective, _runtime, _message, order = solve_order(foundations, limits, rules)
    assert status == "OPTIMAL"
    assert set(order[:2]) == {"A", "C"}
    assert set(order[2:]) == {"B", "D"}
    assert evaluate(foundations, limits, rules, order).validation_status == "Passed"
    assert evaluate(foundations, limits, rules, ["B", "A", "C", "D"]).validation_status == "Failed"
    placed = [
        foundation(
            "A",
            easting_m=Decimal(0),
            northing_m=Decimal(0),
            attributes={"Shallow location": False},
        ),
        foundation(
            "B",
            easting_m=Decimal(1),
            northing_m=Decimal(0),
            attributes={"Shallow location": True},
        ),
        foundation(
            "C",
            easting_m=Decimal(100),
            northing_m=Decimal(0),
            attributes={"Shallow location": False},
        ),
        foundation(
            "D",
            easting_m=Decimal(101),
            northing_m=Decimal(0),
            attributes={"Shallow location": True},
        ),
    ]
    joint = rules + [
        constraint(
            "Distance",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
        )
    ]
    joint_status, joint_objective, _runtime, _message, joint_order = solve_order(
        placed, limits, joint
    )
    assert joint_status == "OPTIMAL"
    assert set(joint_order[:2]) == {"A", "C"}
    assert set(joint_order[2:]) == {"B", "D"}
    assert joint_objective == 200


def test_earliest_trip_keeps_one_location_out_of_the_first_trip():
    foundations = [foundation("A"), foundation("B"), foundation("C"), foundation("D")]
    limits = vessel(max_foundations_per_trip=2)
    rules = [
        constraint(
            "D from trip 2",
            "earliest_sequence",
            {"foundation_id": "D", "earliest_trip": 2},
        )
    ]
    status, _objective, _runtime, _message, order = solve_order(foundations, limits, rules)
    assert status == "OPTIMAL"
    assert order.index("D") >= 2
    review = evaluate(foundations, limits, rules, order)
    assert review.validation_status == "Passed"
    assert any(
        row.check_name == "Earliest trip" and row.target == "trip >= 2"
        for row in review.validation_rows
    )


def test_earliest_trip_form_saves_the_attribute_and_ignores_a_location():
    foundations = [
        foundation("A", attributes={"Shallow location": True}),
        foundation("B", attributes={"Shallow location": False}),
    ]
    form = ConstraintForm(
        data={
            "name": "No shallow first",
            "description": "",
            "enforcement": "hard",
            "active": "on",
            "selector": "attribute",
            "foundation_id": "A",
            "attribute": "Shallow location",
            "operator": "equals",
            "value": "YES",
            "earliest_trip": "2",
        },
        constraint_type="earliest_sequence",
        foundation_ids=["A", "B"],
        columns=["Jacking difficulty", "Shallow location"],
        foundations=foundations,
        vessel=vessel(max_foundations_per_trip=4),
        columns_present={"Jacking difficulty", "Shallow location"},
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["parameters"] == {
        "attribute": "Shallow location",
        "operator": "equals",
        "value": "YES",
        "earliest_trip": 2,
    }
    saved = Constraint(
        name="No shallow first",
        constraint_type="earliest_sequence",
        enforcement="hard",
        parameters_json=form.cleaned_data["parameters"],
    )
    assert saved.parameter_summary == "Shallow location equals YES, earliest trip 2"
    assert "foundation_id" not in form.cleaned_data["parameters"]
    location = ConstraintForm(
        data={
            "name": "D from trip 2",
            "description": "",
            "enforcement": "hard",
            "selector": "foundation",
            "foundation_id": "B",
            "attribute": "Shallow location",
            "operator": "equals",
            "value": "YES",
            "earliest_trip": "2",
        },
        constraint_type="earliest_sequence",
        foundation_ids=["A", "B"],
        columns=["Shallow location"],
        foundations=foundations,
        vessel=vessel(max_foundations_per_trip=4),
        columns_present={"Shallow location"},
    )
    assert location.is_valid(), location.errors
    assert location.cleaned_data["parameters"] == {"foundation_id": "B", "earliest_trip": 2}


def test_second_step_reverses_a_trip_to_shorten_the_link():
    from apps.optimisation.services.between_trips import optimise_trip_connections

    foundations = [
        foundation("A", easting_m=Decimal(0), northing_m=Decimal(0)),
        foundation("B", easting_m=Decimal(3), northing_m=Decimal(0)),
        foundation("D", easting_m=Decimal(8), northing_m=Decimal(0)),
        foundation("C", easting_m=Decimal(4), northing_m=Decimal(0)),
    ]
    rules = [
        constraint(
            "Infield sailing optimization FOU",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
        )
    ]
    limits = vessel(max_foundations_per_trip=2)
    original = ["A", "B", "D", "C"]
    order = optimise_trip_connections(original, foundations, limits, rules)
    assert {frozenset(order[:2]), frozenset(order[2:])} == {
        frozenset({"A", "B"}),
        frozenset({"C", "D"}),
    }
    assert _within_trip_path(foundations, order, 2) == _within_trip_path(foundations, original, 2)
    assert _path(foundations, order) == 8
    assert _path(foundations, order) < _path(foundations, original)


def test_second_step_keeps_a_shallow_location_out_of_trip_one():
    from apps.optimisation.services.between_trips import optimise_trip_connections

    foundations = [
        foundation(
            "A",
            easting_m=Decimal(0),
            northing_m=Decimal(0),
            attributes={"Shallow location": False},
        ),
        foundation(
            "B",
            easting_m=Decimal(10),
            northing_m=Decimal(0),
            attributes={"Shallow location": False},
        ),
        foundation(
            "C",
            easting_m=Decimal(1),
            northing_m=Decimal(0),
            attributes={"Shallow location": True},
        ),
        foundation(
            "D",
            easting_m=Decimal(2),
            northing_m=Decimal(0),
            attributes={"Shallow location": False},
        ),
    ]
    rules = [
        constraint(
            "No shallow in trip 1",
            "earliest_sequence",
            {
                "attribute": "Shallow location",
                "operator": "equals",
                "value": "YES",
                "earliest_trip": 2,
            },
        ),
        constraint(
            "Infield sailing optimization FOU",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
        ),
    ]
    limits = vessel(max_foundations_per_trip=2)
    order = optimise_trip_connections(["A", "B", "C", "D"], foundations, limits, rules)
    assert order == ["B", "A", "C", "D"]
    assert evaluate(foundations, limits, rules, order).validation_status == "Passed"


def test_second_step_does_not_reverse_a_spider_prefix():
    from apps.optimisation.services.between_trips import optimise_trip_connections

    foundations = [
        foundation(
            "S",
            easting_m=Decimal(0),
            northing_m=Decimal(0),
            attributes={"Spider location": True},
        ),
        foundation(
            "N",
            easting_m=Decimal(1),
            northing_m=Decimal(0),
            attributes={"Spider location": False},
        ),
        foundation(
            "Y",
            easting_m=Decimal(10),
            northing_m=Decimal(0),
            attributes={"Spider location": False},
        ),
        foundation(
            "X",
            easting_m=Decimal(3),
            northing_m=Decimal(0),
            attributes={"Spider location": False},
        ),
    ]
    rules = [
        constraint(
            "Spider locations FOU",
            "matching_installed_first",
            {"attribute": "Spider location", "operator": "equals", "value": "YES"},
        ),
        constraint(
            "Infield sailing optimization FOU",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
        ),
    ]
    limits = vessel(max_foundations_per_trip=2)
    order = optimise_trip_connections(["S", "N", "Y", "X"], foundations, limits, rules)
    assert order == ["S", "N", "X", "Y"]
    assert evaluate(foundations, limits, rules, order).validation_status == "Passed"


def _within_trip_path(foundations, names: list[str], capacity: int) -> int:
    total = 0
    for start in range(0, len(names), capacity):
        total += _path(foundations, names[start : start + capacity])
    return total


def _path(foundations, names: list[str]) -> int:
    from apps.optimisation.services.routing import metres_between

    by_id = {item.foundation_id: item for item in foundations}
    points = [by_id[name] for name in names]
    return sum(metres_between(left, right) for left, right in zip(points, points[1:], strict=False))
