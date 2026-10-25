"""Convert stored foundation rows into solver inputs."""

from __future__ import annotations

from decimal import Decimal

from apps.datasets.models import Foundation
from apps.optimisation.services.types import FoundationInput


def to_foundation_input(row: Foundation) -> FoundationInput:
    return FoundationInput(
        foundation_id=row.foundation_id,
        include=bool(row.include),
        weight_t=row.weight_t,
        delivery_sequence=row.delivery_sequence,
        length_m=row.length_m,
        delivery_batch=row.delivery_batch,
        easting_m=row.easting_m,
        northing_m=row.northing_m,
        punch_through=row.punch_through,
        difficulty_value=row.difficulty_value,
        eccentricity_limit_m=row.eccentricity_limit_m,
        fixed_trip=row.fixed_trip,
        fixed_position=row.fixed_position,
        earliest_sequence=row.earliest_sequence,
        latest_sequence=row.latest_sequence,
        notes=row.notes,
        attributes=dict(row.attributes or {}),
    )


def location_coordinates(*groups) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    coordinates: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    for group in groups:
        for row in group:
            identity = getattr(row, "foundation_id", None) or getattr(row, "wtg_id", "")
            coordinates.setdefault(identity.casefold(), (row.easting_m, row.northing_m))
    return coordinates


def cable_activity(row, coordinates: dict[str, tuple]) -> FoundationInput:
    easting, northing = _midpoint(
        coordinates.get(row.start_location_id.casefold()),
        coordinates.get(row.end_location_id.casefold()),
    )
    return FoundationInput(
        foundation_id=row.cable_id,
        include=bool(row.include),
        weight_t=None,
        easting_m=easting,
        northing_m=northing,
        attributes={
            "Cable ID": row.cable_id,
            "Nickname": row.nickname,
            "String ID": row.string_id,
            "Loop ID": row.loop_id,
            "Start location": row.start_location_id,
            "End location": row.end_location_id,
            "Spider cable": row.spider_cable,
        },
    )


def wtg_activity(row) -> FoundationInput:
    return FoundationInput(
        foundation_id=row.wtg_id,
        include=bool(row.include),
        weight_t=None,
        easting_m=row.easting_m,
        northing_m=row.northing_m,
        attributes={
            "Structure": row.structure,
            "Spider location": row.spider_location,
            "String": row.string_label,
            "Jacking difficulty WTG": row.jacking_difficulty,
        },
    )


def _midpoint(start, end):
    if not start or not end or None in (*start, *end):
        return None, None
    return (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
