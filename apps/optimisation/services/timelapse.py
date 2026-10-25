"""Points for the installation timelapse.

FOU and WTG share one calendar. Installation sequence 1 uses programme slot 1
of that package, sequence 2 uses slot 2, and so on. A slot is not a location id.
IAC is left out of the plot. Coordinates come from the dataset stored with the
run. Nothing about a particular project layout is fixed here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.optimisation.models import OptimisationRun
from apps.optimisation.services.routing import format_nautical_miles, metres_xy

_PLOTTED = ("FOU", "WTG")
_WINDOWS = {
    "FOU": ("fou_p50_start", "fou_p50_end"),
    "WTG": ("wtg_p50_start", "wtg_p50_end"),
}
_NO_DATES = (
    "This dataset has no programme dates for the sequenced FOU and WTG locations, "
    "so the calendar plot is not drawn."
)


def timelapse_payload(run: OptimisationRun) -> dict[str, Any]:
    sequence = list(run.sequence_rows.all().order_by("package", "installation_sequence"))
    grouped = {package: [] for package in _PLOTTED}
    for row in sequence:
        package = _package(row)
        if package in grouped:
            grouped[package].append(row)
    plotted = [row for rows in grouped.values() for row in rows]
    if not plotted:
        return _empty()
    slots = {slot.slot: slot for slot in run.dataset_version.programme_slots.all()}
    coverage = {
        package: _coverage(rows, slots, package) for package, rows in grouped.items() if rows
    }
    if all(dated == 0 for dated, _total in coverage.values()):
        return _empty(notice=_NO_DATES)
    if any(dated != total for dated, total in coverage.values()):
        detail = ", ".join(
            f"{package} {dated}/{total}" for package, (dated, total) in coverage.items()
        )
        return _empty(
            notice=(
                "Programme dates do not cover every sequenced FOU and WTG location, "
                f"so the calendar plot is not drawn. {detail}."
            )
        )
    located = {
        "FOU": {row.foundation_id: row for row in run.dataset_version.foundations.all()},
        "WTG": {row.wtg_id: row for row in run.dataset_version.wtg_locations.all()},
    }
    activities = []
    missing = []
    for package, rows in grouped.items():
        for row in rows:
            place = located[package].get(row.foundation_id)
            if place is None or place.easting_m is None or place.northing_m is None:
                missing.append(f"{package} {row.foundation_id}")
                continue
            start, end = _window(slots[row.installation_sequence], package)
            activities.append(
                {
                    "package": package,
                    "marker": "square" if package == "WTG" else "circle",
                    "seq": row.installation_sequence,
                    "trip": row.trip,
                    "pos": row.vessel_position,
                    "id": row.foundation_id,
                    "x": float(place.easting_m),
                    "y": float(place.northing_m),
                    "start": _ms(start),
                    "end": _ms(end),
                }
            )
    if missing or not activities:
        return _empty(missing=missing)
    activities.sort(key=lambda item: (item["start"], item["package"], item["seq"]))
    return {
        "activities": activities,
        "missing": [],
        "within_trip": _within_trip_caption(activities),
        "notice": "",
        "player": {
            "activities": activities,
            "origin": min(item["start"] for item in activities),
            "horizon": max(item["end"] for item in activities),
        },
    }


def _package(row) -> str:
    package = str(row.package or "FOU").strip().upper()
    if package not in {"FOU", "IAC", "WTG"}:
        return "FOU"
    return package


def _coverage(rows, slots, package: str) -> tuple[int, int]:
    dated = sum(1 for row in rows if _window(slots.get(row.installation_sequence), package))
    return dated, len(rows)


def _window(slot, package: str) -> tuple[datetime, datetime] | None:
    if slot is None:
        return None
    start_name, end_name = _WINDOWS[package]
    start = getattr(slot, start_name)
    end = getattr(slot, end_name)
    if start is None or end is None or end <= start:
        return None
    return start, end


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _within_trip_caption(activities: list[dict[str, Any]]) -> str:
    parts = []
    for package in _PLOTTED:
        frames = [item for item in activities if item["package"] == package]
        if len(frames) < 2:
            continue
        parts.append(f"{package} {format_nautical_miles(_within_trip_metres(frames))}")
    return " · ".join(parts)


def _within_trip_metres(frames: list[dict[str, Any]]) -> int:
    ordered = sorted(frames, key=lambda item: item["seq"])
    total = 0
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left["trip"] != right["trip"]:
            continue
        total += metres_xy(
            Decimal(str(left["x"])),
            Decimal(str(left["y"])),
            Decimal(str(right["x"])),
            Decimal(str(right["y"])),
        )
    return total


def _empty(*, missing: list[str] | None = None, notice: str = "") -> dict[str, Any]:
    return {
        "activities": [],
        "missing": missing or [],
        "within_trip": "",
        "notice": notice,
        "player": None,
    }
