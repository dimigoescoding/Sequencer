"""Datatypes shared by validation, optimisation, and export.

These objects are plain values. Services do not read Django models directly so
the same checks can run in tests without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class FoundationInput:
    foundation_id: str
    include: bool
    weight_t: Decimal | None
    delivery_sequence: int | None = None
    length_m: Decimal | None = None
    delivery_batch: str = ""
    easting_m: Decimal | None = None
    northing_m: Decimal | None = None
    punch_through: bool | None = None
    difficulty_value: Decimal | None = None
    eccentricity_limit_m: Decimal | None = None
    fixed_trip: int | None = None
    fixed_position: int | None = None
    earliest_sequence: int | None = None
    latest_sequence: int | None = None
    notes: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VesselConfig:
    max_foundations_per_trip: int
    allow_partial_final_trip: bool
    base_maximum_trip_payload_t: Decimal | None = None
    solver_time_limit_seconds: int = 60
    transit_speed_knots: Decimal | None = None
    harbour_easting_m: Decimal | None = None
    harbour_northing_m: Decimal | None = None
    wtg_per_trip: int = 4


@dataclass(frozen=True)
class ConstraintInput:
    name: str
    constraint_type: str
    parameters: dict[str, Any]
    enforcement: str
    active: bool = True
    severity: int | None = None
    description: str = ""
    scope: str = ""
    display_order: int = 0
    constraint_id: int | None = None
    package: str = "FOU"


@dataclass
class SequenceRow:
    installation_sequence: int
    trip: int
    vessel_position: int
    foundation_id: str
    weight_t: Decimal | None
    trip_total_weight_t: Decimal | None
    delivery_sequence: int | None
    sequence_deviation: int | None
    delivery_batch: str
    difficulty_value: Decimal | None
    punch_through: bool | None
    fixed_trip: int | None
    fixed_position: int | None
    earliest_sequence: int | None
    latest_sequence: int | None
    hard_constraint_status: str
    soft_penalty: int
    governing_constraints: str
    notes: str
    package: str = "FOU"


@dataclass
class TripRow:
    trip: int
    foundation_count: int
    foundations_in_order: str
    payload_limit_t: Decimal | None
    total_weight_t: Decimal
    remaining_payload_t: Decimal | None
    punch_through_count: int
    average_difficulty: Decimal | None
    maximum_difficulty: Decimal | None
    route_distance: Decimal | None
    payload_check: str
    position_check: str
    overall_trip_check: str
    package: str = "FOU"


@dataclass
class CampaignResult:
    package: str
    items: list[FoundationInput]
    order: list[str]
    vessel: VesselConfig
    constraints: list[ConstraintInput]


@dataclass
class ValidationRow:
    check_name: str
    constraint_name: str
    target: str
    actual_result: str
    status: str
    affected_foundations: str
    explanation: str
    display_order: int


@dataclass
class Evaluation:
    sequence_rows: list[SequenceRow] = field(default_factory=list)
    trip_rows: list[TripRow] = field(default_factory=list)
    validation_rows: list[ValidationRow] = field(default_factory=list)
    validation_status: str = "Failed"
    soft_tradeoff_count: int = 0
    hard_failures: int = 0
    objective_penalty: int = 0


@dataclass
class Outcome:
    status: str
    solver_status: str
    validation_status: str
    objective_value: int | None
    runtime_seconds: float
    message: str
    seed: int
    conflicts: list[str] = field(default_factory=list)
    blocked: bool = False
    sequence_rows: list[SequenceRow] = field(default_factory=list)
    trip_rows: list[TripRow] = field(default_factory=list)
    validation_rows: list[ValidationRow] = field(default_factory=list)
    included_count: int = 0
    trip_count: int = 0
    hard_constraint_count: int = 0
    soft_constraint_count: int = 0
    soft_tradeoff_count: int = 0
