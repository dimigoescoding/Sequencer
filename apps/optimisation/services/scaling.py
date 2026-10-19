"""Penalty scaling shared by the CP-SAT objective and the independent validator.

Each soft constraint produces a raw penalty R in its own units and a proven
upper bound M for that raw value on this dataset. The objective contribution is

    ceil(R * severity * 1000 / M)

so every soft constraint is mapped onto 0..1000 before severity is applied.
A severity of 100 is exactly twice a severity of 50 for the same raw ratio.

Hard distance minimisation has no numeric limit. It is placed on the objective
with PRIMARY_WEIGHT per metre, which is larger than the maximum combined soft
penalty, so one metre is never traded away for a soft preference. That is not
a relaxation and it is not rescaled into the soft band.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

NORM = 1000
PRIMARY_WEIGHT = 10_000_000
SOLVER_SEED = 1
# Sized for one Render Free web instance: 512 MB RAM and 0.1 CPU.
MAX_INCLUDED_FOUNDATIONS = 40
MAX_DISTANCE_FOUNDATIONS = 20
MAX_SOLVER_TIME_LIMIT_SECONDS = 30


def scaled_penalty(raw: int, max_raw: int, severity: int) -> int:
    if raw <= 0 or max_raw <= 0 or severity <= 0:
        return 0
    return (raw * severity * NORM + max_raw - 1) // max_raw


def weight_kg(weight_t: Decimal) -> int:
    return int((weight_t * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def scaled_attribute(value: Decimal) -> int:
    return int((value * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
