"""Convert stored foundation rows into solver inputs."""

from __future__ import annotations

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
