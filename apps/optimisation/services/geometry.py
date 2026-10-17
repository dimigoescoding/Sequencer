"""Trip and vessel-position formulas.

For a maximum of N foundations per trip and a 1-based installation sequence:

    trip = floor((sequence_position - 1) / N) + 1
    vessel_position = ((sequence_position - 1) mod N) + 1
"""

from __future__ import annotations


def required_trips(count: int, per_trip: int) -> int:
    if count <= 0 or per_trip <= 0:
        return 0
    return (count + per_trip - 1) // per_trip


def trip_number(sequence: int, per_trip: int) -> int:
    return (sequence - 1) // per_trip + 1


def vessel_position(sequence: int, per_trip: int) -> int:
    return (sequence - 1) % per_trip + 1


def trip_slot_count(trip: int, count: int, per_trip: int) -> int:
    trips = required_trips(count, per_trip)
    if trip < 1 or trip > trips:
        return 0
    if trip < trips:
        return per_trip
    return count - (trips - 1) * per_trip


def sequence_positions_for_trip(trip: int, count: int, per_trip: int) -> list[int]:
    slots = trip_slot_count(trip, count, per_trip)
    if slots <= 0:
        return []
    start = (trip - 1) * per_trip + 1
    return list(range(start, start + slots))


def positions_in_trip_window(
    start_trip: int, end_trip: int, count: int, per_trip: int
) -> list[int]:
    positions: list[int] = []
    for trip in range(start_trip, end_trip + 1):
        positions.extend(sequence_positions_for_trip(trip, count, per_trip))
    return positions
