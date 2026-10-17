"""Pre-solver conflict detection."""

from apps.optimisation.services.conflicts import find_conflicts
from tests.support import constraint, foundation, vessel

COLUMNS = {
    "Foundation_ID",
    "Include",
    "Weight_t",
    "Delivery_Sequence",
    "Punch_Through",
    "Easting_m",
    "Northing_m",
    "Difficulty_Value",
}


def _messages(*constraints, foundations=None, settings=None, columns=None) -> list[str]:
    return find_conflicts(
        foundations
        or [
            foundation("A", 300),
            foundation("B", 300),
            foundation("C", 100),
        ],
        settings or vessel(max_foundations_per_trip=2),
        list(constraints),
        columns or COLUMNS,
    )


def test_contradictory_fixed_trips():
    messages = _messages(
        constraint("Trip 1", "fixed_trip", {"foundation_id": "A", "trip_number": 1}),
        constraint("Trip 2", "fixed_trip", {"foundation_id": "A", "trip_number": 2}),
    )
    assert any("more than one trip" in message for message in messages)


def test_invalid_vessel_position():
    messages = _messages(
        constraint(
            "Too far aft", "fixed_vessel_position", {"foundation_id": "A", "position_number": 5}
        ),
    )
    assert any("position 5" in message for message in messages)


def test_missing_required_input_column():
    messages = _messages(
        constraint(
            "Route",
            "minimise_within_trip_distance",
            {"include_harbour_legs": False},
            enforcement="soft",
            severity=20,
        ),
        columns={"Foundation_ID", "Include", "Weight_t", "Delivery_Sequence"},
        foundations=[foundation("A", 100, easting_m=None, northing_m=None)],
        settings=vessel(max_foundations_per_trip=1),
    )
    assert any("Easting_m and Northing_m" in message for message in messages)


def test_grouping_and_separation_conflict():
    messages = _messages(
        constraint("Together", "same_trip", {"foundation_ids": ["A", "B"]}),
        constraint("Apart", "separate_trip", {"foundation_ids": ["A", "B"]}),
    )
    assert any("same-trip" in message for message in messages)


def test_fixed_trip_payload_conflict():
    messages = _messages(
        constraint("Limit", "maximum_trip_payload", {"maximum_payload_t": "500"}),
        constraint("A on 1", "fixed_trip", {"foundation_id": "A", "trip_number": 1}),
        constraint("B on 1", "fixed_trip", {"foundation_id": "B", "trip_number": 1}),
    )
    assert any("above the hard payload" in message for message in messages)


def test_spreadsheet_position_above_capacity():
    messages = find_conflicts(
        [foundation("A", 100, fixed_position=6)],
        vessel(max_foundations_per_trip=4),
        [],
        COLUMNS,
    )
    assert any("Fixed_Position 6" in message for message in messages)


def test_minimum_count_above_capacity():
    messages = _messages(
        constraint(
            "Too many",
            "minimum_matching_per_trip",
            {
                "attribute": "Punch_Through",
                "operator": "equals",
                "value": "Yes",
                "minimum_count": 3,
            },
        ),
        foundations=[
            foundation("A", 100, punch_through=True),
            foundation("B", 100, punch_through=True),
            foundation("C", 100, punch_through=True),
        ],
    )
    assert any("above the trip capacity" in message for message in messages)


def test_unknown_foundation_reference():
    messages = _messages(
        constraint("Missing", "fixed_trip", {"foundation_id": "ZZ", "trip_number": 1})
    )
    assert any(
        "ZZ" in message and ("does not exist" in message or "not an included foundation" in message)
        for message in messages
    )
