"""Explain which constraint types the current dataset can support."""

from __future__ import annotations

from apps.constraints.library import TYPE_ORDER
from apps.constraints.services.matching import column_state
from apps.optimisation.services.types import FoundationInput, VesselConfig


def availability_reasons(
    foundations: list[FoundationInput],
    columns_present: set[str],
    vessel: VesselConfig | None = None,
) -> dict[str, str]:
    """Return a disable reason for each unavailable type. Available types map to ''."""
    state = column_state(foundations, columns_present)
    included = [item for item in foundations if item.include]
    reasons = dict.fromkeys(TYPE_ORDER, "")
    if not included:
        for key in reasons:
            reasons[key] = "Include at least one foundation before adding constraints."
        return reasons

    if not (state["Easting_m"]["complete"] and state["Northing_m"]["complete"]):
        reasons["minimise_within_trip_distance"] = (
            "Distance constraints require Easting_m and Northing_m on every included foundation. "
            "Missing coordinates do not block other constraint types."
        )
    if not state["Difficulty_Value"]["complete"]:
        reasons["difficulty_progression"] = (
            "Difficulty progression requires Difficulty_Value on every included foundation."
        )
    if "Loop ID" not in columns_present:
        reasons["loop_id_sequence"] = (
            "Loop ID sequence requires the Loop ID column on the IAC sheet."
        )
    if "String ID" not in columns_present:
        reasons["string_id_sequence"] = (
            "String ID sequence requires the String ID column on the IAC sheet."
        )
    if not state["Delivery_Sequence"]["complete"]:
        reasons["delivery_sequence_alignment"] = (
            "Delivery-sequence alignment requires Delivery_Sequence on every included foundation."
        )
    if not state["Punch_Through"]["present"] or not state["Punch_Through"]["any"]:
        # The type stays available for other attributes. The form explains Punch_Through specifically.
        pass
    if vessel is not None and vessel.max_foundations_per_trip < 1:
        for key in reasons:
            if not reasons[key]:
                reasons[key] = (
                    "Set a positive maximum foundations per trip before adding constraints."
                )
    return reasons


def punch_through_explanation(foundations: list[FoundationInput], columns_present: set[str]) -> str:
    state = column_state(foundations, columns_present)["Punch_Through"]
    if not state["present"]:
        return (
            "Punch-through rules require the Punch_Through column. "
            "Upload a dataset that includes it before writing a Punch_Through rule."
        )
    if not state["any"]:
        return (
            "Punch-through rules require Punch_Through values. "
            "Every included foundation currently has a blank Punch_Through cell."
        )
    return ""
