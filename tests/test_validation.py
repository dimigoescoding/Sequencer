"""Independent validation does not trust the solver."""

from apps.optimisation.services.evaluation import evaluate
from tests.support import constraint, foundation, vessel


def _check(result, name: str):
    return next(row for row in result.validation_rows if row.check_name == name)


def test_duplicate_result_fails():
    foundations = [foundation("A"), foundation("B")]
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), [], ["A", "A"])
    assert result.validation_status == "Failed"
    assert _check(result, "Unique Foundation_ID").status == "Failed"


def test_missing_foundation_fails():
    foundations = [foundation("A"), foundation("B")]
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), [], ["A"])
    assert result.validation_status == "Failed"
    assert "B" in _check(result, "Included foundations present").affected_foundations


def test_payload_violation_fails():
    foundations = [foundation("A", 300), foundation("B", 300), foundation("C", 100)]
    constraints = [constraint("Payload", "maximum_trip_payload", {"maximum_payload_t": "500"})]
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), constraints, ["A", "B", "C"])
    assert result.validation_status == "Failed"
    assert any(
        row.status == "Failed" and "payload" in row.check_name.casefold()
        for row in result.validation_rows
    )


def test_fixed_position_violation_fails():
    foundations = [foundation("A"), foundation("B")]
    constraints = [
        constraint(
            "A first", "fixed_vessel_position", {"foundation_id": "A", "position_number": 1}
        ),
    ]
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), constraints, ["B", "A"])
    assert result.validation_status == "Failed"
    assert any(
        row.status == "Failed" and row.constraint_name == "A first"
        for row in result.validation_rows
    )


def test_sequence_window_violation_fails():
    foundations = [foundation("A"), foundation("B")]
    constraints = [
        constraint("A later", "earliest_sequence", {"foundation_id": "A", "earliest_sequence": 2})
    ]
    result = evaluate(foundations, vessel(max_foundations_per_trip=2), constraints, ["A", "B"])
    assert result.validation_status == "Failed"
    assert any(
        row.status == "Failed" and row.constraint_name == "A later"
        for row in result.validation_rows
    )
