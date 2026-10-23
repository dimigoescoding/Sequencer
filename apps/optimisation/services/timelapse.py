"""Points for the installation timelapse.

Coordinates come from the dataset stored with the run. Nothing about a
particular project layout is fixed here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.optimisation.models import OptimisationRun
from apps.optimisation.services.routing import format_nautical_miles, metres_xy


def timelapse_payload(run: OptimisationRun) -> dict[str, Any]:
    sequence = list(run.sequence_rows.all().order_by("installation_sequence"))
    if not sequence:
        return {"frames": [], "missing": [], "within_trip": ""}
    located = {
        row.foundation_id: row
        for row in run.dataset_version.foundations.all()
    }
    frames = []
    missing = []
    for row in sequence:
        foundation = located.get(row.foundation_id)
        if (
            foundation is None
            or foundation.easting_m is None
            or foundation.northing_m is None
        ):
            missing.append(row.foundation_id)
            continue
        frames.append(
            {
                "seq": row.installation_sequence,
                "trip": row.trip,
                "pos": row.vessel_position,
                "id": row.foundation_id,
                "x": float(foundation.easting_m),
                "y": float(foundation.northing_m),
            }
        )
    within = _within_trip_metres(frames) if frames and not missing else None
    return {
        "frames": frames if not missing else [],
        "missing": missing,
        "within_trip": "" if within is None else format_nautical_miles(within),
    }


def _within_trip_metres(frames: list[dict[str, Any]]) -> int:
    total = 0
    for left, right in zip(frames, frames[1:], strict=False):
        if left["trip"] != right["trip"]:
            continue
        total += metres_xy(
            Decimal(str(left["x"])),
            Decimal(str(left["y"])),
            Decimal(str(right["x"])),
            Decimal(str(right["y"])),
        )
    return total
