"""Supported constraint library for MVP 1.

The library describes constraint types the user can configure. It does not
contain project-specific engineering limits, payloads, or sequences.
"""

from __future__ import annotations

CONSTRAINT_TYPES: dict[str, dict[str, str]] = {
    "maximum_trip_payload": {
        "label": "Maximum trip payload",
        "summary": (
            "The sum of Weight_t on each trip must stay within maximum_payload_t. "
            "Used as a hard limit unless you explicitly choose soft. A soft payload "
            "limit permits an overloaded trip and penalises the excess."
        ),
    },
    "fixed_trip": {
        "label": "Fixed trip",
        "summary": "Assign one foundation to one trip number.",
    },
    "fixed_vessel_position": {
        "label": "Fixed vessel position",
        "summary": (
            "Assign one foundation to a vessel position. Add a trip number when both "
            "the trip and the position are fixed."
        ),
    },
    "allowed_positions": {
        "label": "Allowed vessel positions by attribute",
        "summary": (
            "Foundations that match the attribute rule may only use the selected vessel positions."
        ),
    },
    "excluded_positions": {
        "label": "Excluded vessel positions by attribute",
        "summary": "Foundations that match the attribute rule must not use the selected positions.",
    },
    "earliest_sequence": {
        "label": "Earliest trip",
        "summary": (
            "One location, or every location matching an attribute, is not installed before "
            "this trip. Trip 2 keeps those locations out of the first trip."
        ),
    },
    "latest_sequence": {
        "label": "Latest sequence position",
        "summary": "A foundation, or foundations matching a rule, cannot be installed after this point.",
    },
    "precedence": {
        "label": "Precedence",
        "summary": (
            "The successor installation sequence must be at least minimum_gap positions "
            "after the predecessor. maximum_gap is optional."
        ),
    },
    "maximum_matching_per_trip": {
        "label": "Maximum matching foundations per trip",
        "summary": "Limit how many foundations matching an attribute rule share a trip.",
    },
    "minimum_matching_per_trip": {
        "label": "Minimum matching foundations per trip",
        "summary": "Require a minimum number of matching foundations on each applicable trip.",
    },
    "same_trip": {
        "label": "Same-trip grouping",
        "summary": "The selected foundations are placed on the same trip.",
    },
    "separate_trip": {
        "label": "Separate-trip rule",
        "summary": "The selected foundations are not placed on the same trip.",
    },
    "attribute_ordering": {
        "label": "Attribute ordering",
        "summary": "Order a numeric attribute over the full sequence or within each trip.",
    },
    "delivery_sequence_alignment": {
        "label": "Delivery-sequence alignment",
        "summary": (
            "Penalise absolute deviation between Delivery_Sequence and the installation "
            "sequence. Deviation inside the tolerance has no penalty."
        ),
    },
    "difficulty_progression": {
        "label": "Difficulty progression",
        "summary": (
            "Prefer easier foundations earlier when direction is ascending, across the selected trips. "
            "You set the strength with severity."
        ),
    },
    "minimise_within_trip_distance": {
        "label": "Minimise total sailing distance",
        "summary": (
            "Minimise the straight-line distance from each foundation to the next across "
            "the full sequence. That includes the sail inside a trip and the sail from the "
            "end of one trip to the start of the next. Harbour transit is not included. "
            "The solver chooses trip membership and the route together. No map is drawn."
        ),
    },
    "matching_installed_first": {
        "label": "Matching locations first",
        "summary": (
            "Locations that match the attribute occupy the first positions, in any order among themselves."
        ),
    },
    "avoid_matching_in_first_trips": {
        "label": "Avoid matches in the first trips",
        "summary": "Matching locations are kept out of the first trips named by the rule.",
    },
}

TYPE_ORDER: list[str] = list(CONSTRAINT_TYPES)
