"""Euclidean distances in metres. No map geometry is produced.

The solver keeps integer metres. Screens and the Excel export show nautical miles.
One nautical mile is 1,852 metres.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.optimisation.services.types import FoundationInput, VesselConfig

NAUTICAL_MILE_M = Decimal("1852")


def metres_between(left: FoundationInput, right: FoundationInput) -> int:
    return metres_xy(left.easting_m, left.northing_m, right.easting_m, right.northing_m)


def metres_xy(
    east_a: Decimal | None,
    north_a: Decimal | None,
    east_b: Decimal | None,
    north_b: Decimal | None,
) -> int:
    if None in {east_a, north_a, east_b, north_b}:
        return 0
    distance = math.hypot(float(east_a) - float(east_b), float(north_a) - float(north_b))
    return int(Decimal(str(distance)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def nautical_miles(metres: int | Decimal) -> Decimal:
    return (Decimal(metres) / NAUTICAL_MILE_M).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def format_nautical_miles(metres: int | Decimal) -> str:
    return f"{nautical_miles(metres)} nm"


def harbour_coordinates(
    parameters: dict[str, Any], vessel: VesselConfig
) -> tuple[Decimal, Decimal] | None:
    if not parameters.get("include_harbour_legs"):
        return None
    east = parameters.get("harbour_easting_m")
    north = parameters.get("harbour_northing_m")
    if east not in (None, "") and north not in (None, ""):
        return Decimal(str(east)), Decimal(str(north))
    if vessel.harbour_easting_m is not None and vessel.harbour_northing_m is not None:
        return vessel.harbour_easting_m, vessel.harbour_northing_m
    return None
