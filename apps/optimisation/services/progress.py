"""Cumulative installation progress for one stored sequence.

Sequence position N uses programme slot N. A location counts as installed at
the end of that activity. A missing end date leaves that point off the curve.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.optimisation.models import OptimisationRun

_SERIES = (
    ("MP Installed", "#1f77b4", "FOU", "fou_p50_end"),
    ("SSt Installed", "#9467bd", "FOU", "sst_p50_end"),
    ("Filter Layer", "#17becf", "FOU", "filter_p50_end"),
    ("Armour Layer", "#8c564b", "FOU", "armour_p50_end"),
    ("IAC Lay", "#2ca02c", "IAC", "iac_p50_end"),
    ("IAC Burial", "#bcbd22", "IAC", "burial_p50_end"),
    ("WTG Installed", "#ff7f0e", "WTG", "wtg_p50_end"),
    ("WTG Commissioned", "#d62728", "WTG", "commissioning_p50_end"),
)
_WIDTH = 960
_HEIGHT = 440
_LEFT = 72
_RIGHT = 24
_TOP = 20
_BOTTOM = 64


def progress_chart(run: OptimisationRun) -> dict | None:
    if run.dataset_version_id is None:
        return None
    grouped = {package: [] for package in ("FOU", "IAC", "WTG")}
    for row in run.sequence_rows.all().order_by("installation_sequence", "id"):
        package = str(row.package or "FOU").strip().upper()
        if package in grouped:
            grouped[package].append(row)
    if not any(grouped.values()):
        return None
    slots = {slot.slot: slot for slot in run.dataset_version.programme_slots.all()}
    built = []
    for name, color, package, field in _SERIES:
        moments = []
        for row in grouped[package]:
            slot = slots.get(row.installation_sequence)
            if slot is None:
                continue
            end = getattr(slot, field, None)
            if not isinstance(end, datetime):
                continue
            moments.append(_aware(end))
        if moments:
            built.append((name, color, sorted(moments)))
    if not built:
        return None
    flat = [moment for _name, _color, moments in built for moment in moments]
    start = min(flat)
    finish = max(flat)
    if finish <= start:
        finish = start + timedelta(days=1)
    ymax = max(_counts(moments)[-1][1] for _name, _color, moments in built)
    span = (finish - start).total_seconds()
    plot_w = _WIDTH - _LEFT - _RIGHT
    plot_h = _HEIGHT - _TOP - _BOTTOM

    def x_of(moment: datetime) -> float:
        return _LEFT + (moment - start).total_seconds() / span * plot_w

    def y_of(count: int) -> float:
        return _TOP + (1 - count / ymax) * plot_h

    series = []
    for name, color, moments in built:
        steps = _counts(moments)
        coords = [(x_of(start), y_of(0))]
        previous = 0
        for moment, count in steps:
            coords.append((x_of(moment), y_of(previous)))
            coords.append((x_of(moment), y_of(count)))
            previous = count
        coords.append((x_of(finish), y_of(previous)))
        series.append(
            {
                "name": name,
                "color": color,
                "total": previous,
                "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in coords),
            }
        )
    axis_bottom = _TOP + plot_h
    return {
        "width": _WIDTH,
        "height": _HEIGHT,
        "axis_top": _TOP,
        "axis_bottom": axis_bottom,
        "axis_left": _LEFT,
        "axis_right": _LEFT + plot_w,
        "tick_x": _LEFT - 10,
        "tick_y": axis_bottom + 20,
        "label_x": 18,
        "label_y": _TOP + plot_h / 2,
        "time_x": _LEFT + plot_w / 2,
        "time_y": _HEIGHT - 14,
        "series": series,
        "yticks": [
            {"y": f"{y_of(count):.1f}", "label": str(count)} for count in _axis_counts(ymax)
        ],
        "xticks": [
            {"x": f"{x_of(moment):.1f}", "label": moment.astimezone(UTC).strftime("%Y-%m-%d")}
            for moment in _axis_times(start, finish)
        ],
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _counts(moments: list[datetime]) -> list[tuple[datetime, int]]:
    steps: list[tuple[datetime, int]] = []
    count = 0
    index = 0
    while index < len(moments):
        moment = moments[index]
        while index < len(moments) and moments[index] == moment:
            count += 1
            index += 1
        steps.append((moment, count))
    return steps


def _axis_counts(ymax: int) -> list[int]:
    if ymax <= 4:
        return list(range(ymax + 1))
    step = 1
    while ymax / step > 5:
        step = 2 if step == 1 else 5 if step == 2 else step * 2
    marks = list(range(0, ymax + 1, step))
    if marks[-1] != ymax:
        marks.append(ymax)
    return marks


def _axis_times(start: datetime, finish: datetime) -> list[datetime]:
    span = finish - start
    return [start + span * index / 4 for index in range(5)]
