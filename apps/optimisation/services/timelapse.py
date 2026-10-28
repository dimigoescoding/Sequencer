"""Points for the installation timelapse.

FOU, IAC, and WTG share one calendar. Installation sequence 1 uses programme
slot 1 of that package, sequence 2 uses slot 2, and so on. A slot is not a
location id. SSt installation, filter layer, and armour layer use the FOU
sequence. IAC burial uses the IAC sequence. WTG commissioning uses the WTG
sequence. A slice is omitted when its dates are blank. The OSS id is a label.
Coordinates come from the dataset stored with the run.
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
    "IAC": ("iac_p50_start", "iac_p50_end"),
    "WTG": ("wtg_p50_start", "wtg_p50_end"),
}
_LOCATION_SLICES = (
    ("MP Installed", "#1f77b4", "fou_p50_start", "fou_p50_end"),
    ("S St Installed", "#9467bd", "sst_p50_start", "sst_p50_end"),
    ("Filter Layer", "#17becf", "filter_p50_start", "filter_p50_end"),
    ("Armour Layer", "#8c564b", "armour_p50_start", "armour_p50_end"),
)
_WTG_SLICES = (
    ("WTG Installed", "#ff7f0e", "wtg_p50_start", "wtg_p50_end"),
    ("WTG Commissioned", "#d62728", "commissioning_p50_start", "commissioning_p50_end"),
)
_CABLE_SLICES = (
    ("IAC Lay", "#2ca02c", "iac_p50_start", "iac_p50_end"),
    ("IAC Burial", "#bcbd22", "burial_p50_start", "burial_p50_end"),
)
_NO_DATES = (
    "This dataset has no programme dates for the sequenced FOU and WTG locations, "
    "so the calendar plot is not drawn."
)


def timelapse_payload(run: OptimisationRun) -> dict[str, Any]:
    sequence = list(run.sequence_rows.all().order_by("package", "installation_sequence"))
    grouped = {package: [] for package in ("FOU", "IAC", "WTG")}
    for row in sequence:
        package = _package(row)
        if package in grouped:
            grouped[package].append(row)
    if not any(grouped.values()):
        return _empty()
    slots = {slot.slot: slot for slot in run.dataset_version.programme_slots.all()}
    coverage = {
        package: _coverage(rows, slots, package)
        for package, rows in grouped.items()
        if package in _PLOTTED and rows
    }
    if coverage and all(dated == 0 for dated, _total in coverage.values()):
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
    for package in _PLOTTED:
        rows = grouped[package]
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
    _add_cables(run, grouped["IAC"], slots, activities, missing)
    places = _places(run, grouped, slots, located, missing)
    if missing or not activities:
        return _empty(missing=missing)
    activities.sort(key=lambda item: (item["start"], item["package"], item["seq"]))
    moments = [item["start"] for item in activities] + [item["end"] for item in activities]
    for place in places:
        for sliver in place["slices"]:
            moments.extend((sliver["start"], sliver["end"]))
    return {
        "activities": activities,
        "missing": [],
        "within_trip": _within_trip_caption(activities),
        "notice": "",
        "player": {
            "activities": activities,
            "places": places,
            "labels": _oss_labels(run),
            "origin": min(moments),
            "horizon": max(moments),
        },
    }


def _places(run, grouped, slots, located, missing: list[str]) -> list[dict[str, Any]]:
    """One pizza per sequenced location, and one per cable that has lay or burial dates."""
    places: dict[str, dict[str, Any]] = {}
    for row in grouped["FOU"]:
        _location_place(places, located["FOU"], row, slots, _LOCATION_SLICES, missing)
    for row in grouped["WTG"]:
        _location_place(places, located["WTG"], row, slots, _WTG_SLICES, missing)
    cables = _cable_places(run, grouped["IAC"], slots, missing)
    ordered = sorted(places.values(), key=lambda item: item["id"])
    ordered.extend(cables)
    return ordered


def _location_place(places, located, row, slots, definitions, missing: list[str]) -> None:
    identity = str(row.foundation_id)
    if identity.strip().casefold() == "oss":
        return
    place = located.get(identity)
    if place is None or place.easting_m is None or place.northing_m is None:
        label = f"{_package(row)} {identity}"
        if label not in missing:
            missing.append(label)
        return
    key = identity.casefold()
    entry = places.get(key)
    if entry is None:
        entry = {
            "id": identity,
            "kind": "location",
            "x": float(place.easting_m),
            "y": float(place.northing_m),
            "slices": [],
        }
        places[key] = entry
    entry["slices"].extend(_slices(slots.get(row.installation_sequence), definitions))


def _cable_places(run, rows, slots, missing: list[str]) -> list[dict[str, Any]]:
    coordinates: dict[str, tuple[float, float]] = {}
    for row in run.dataset_version.foundations.all():
        if row.easting_m is None or row.northing_m is None:
            continue
        coordinates[row.foundation_id.casefold()] = (float(row.easting_m), float(row.northing_m))
    for row in run.dataset_version.wtg_locations.all():
        if row.easting_m is None or row.northing_m is None:
            continue
        coordinates.setdefault(row.wtg_id.casefold(), (float(row.easting_m), float(row.northing_m)))
    stored = {row.cable_id.casefold(): row for row in run.dataset_version.cables.all()}
    places = []
    for row in rows:
        slivers = _slices(slots.get(row.installation_sequence), _CABLE_SLICES)
        if not slivers:
            continue
        cable = stored.get(str(row.foundation_id).casefold())
        start = coordinates.get(cable.start_location_id.casefold()) if cable is not None else None
        end = coordinates.get(cable.end_location_id.casefold()) if cable is not None else None
        if start is None or end is None:
            label = f"IAC {row.foundation_id}"
            if label not in missing:
                missing.append(label)
            continue
        places.append(
            {
                "id": row.foundation_id,
                "kind": "cable",
                "x": (start[0] + end[0]) / 2,
                "y": (start[1] + end[1]) / 2,
                "slices": slivers,
            }
        )
    places.sort(key=lambda item: item["id"])
    return places


def _slices(slot, definitions) -> list[dict[str, Any]]:
    if slot is None:
        return []
    slivers = []
    for label, color, start_name, end_name in definitions:
        start = getattr(slot, start_name, None)
        end = getattr(slot, end_name, None)
        if start is None or end is None or end < start:
            continue
        slivers.append({"label": label, "color": color, "start": _ms(start), "end": _ms(end)})
    return slivers


def _oss_labels(run: OptimisationRun) -> list[dict[str, Any]]:
    labels = []
    for row in run.dataset_version.foundations.all():
        if str(row.foundation_id).strip().casefold() != "oss":
            continue
        if row.easting_m is None or row.northing_m is None:
            continue
        labels.append(
            {"id": row.foundation_id, "x": float(row.easting_m), "y": float(row.northing_m)}
        )
    return labels


def _add_cables(run, rows, slots, activities: list[dict[str, Any]], missing: list[str]) -> None:
    places: dict[str, tuple[float, float]] = {}
    for row in run.dataset_version.foundations.all():
        if row.easting_m is None or row.northing_m is None:
            continue
        places[row.foundation_id.casefold()] = (float(row.easting_m), float(row.northing_m))
    for row in run.dataset_version.wtg_locations.all():
        if row.easting_m is None or row.northing_m is None:
            continue
        places.setdefault(row.wtg_id.casefold(), (float(row.easting_m), float(row.northing_m)))
    cables = {row.cable_id.casefold(): row for row in run.dataset_version.cables.all()}
    for row in rows:
        window = _window(slots.get(row.installation_sequence), "IAC")
        if window is None:
            continue
        cable = cables.get(str(row.foundation_id).casefold())
        start = places.get(cable.start_location_id.casefold()) if cable is not None else None
        end = places.get(cable.end_location_id.casefold()) if cable is not None else None
        if start is None or end is None:
            missing.append(f"IAC {row.foundation_id}")
            continue
        start_at, end_at = window
        activities.append(
            {
                "package": "IAC",
                "marker": "line",
                "seq": row.installation_sequence,
                "trip": row.trip,
                "pos": row.vessel_position,
                "id": row.foundation_id,
                "x": start[0],
                "y": start[1],
                "x2": end[0],
                "y2": end[1],
                "start": _ms(start_at),
                "end": _ms(end_at),
            }
        )


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
