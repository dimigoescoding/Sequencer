"""Raw soft-constraint metrics shared by the validator.

The CP-SAT model encodes the same definitions. Both sides then call scaled_penalty.
"""

from __future__ import annotations

from apps.constraints.services.matching import attribute_value
from apps.optimisation.services.scaling import scaled_attribute
from apps.optimisation.services.types import FoundationInput


def ordering_pairs(
    foundations: list[FoundationInput], attribute: str, direction: str
) -> list[tuple[int, int]]:
    values = [scaled_attribute(attribute_value(item, attribute)) for item in foundations]
    pairs: list[tuple[int, int]] = []
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            if values[left] == values[right]:
                continue
            if direction == "ascending":
                earlier, later = (left, right) if values[left] < values[right] else (right, left)
            else:
                earlier, later = (left, right) if values[left] > values[right] else (right, left)
            pairs.append((earlier, later))
    return pairs


def count_inversions(sequence_of_index: list[int], pairs: list[tuple[int, int]]) -> int:
    return sum(
        1 for earlier, later in pairs if sequence_of_index[earlier] > sequence_of_index[later]
    )


def delivery_max_raw(delivery_sequences: list[int], tolerance: int) -> int:
    count = len(delivery_sequences)
    total = 0
    for delivery in delivery_sequences:
        max_deviation = max(abs(1 - delivery), abs(count - delivery))
        total += max(0, max_deviation - tolerance)
    return total


def delivery_excess(sequence: int, delivery: int, tolerance: int) -> int:
    return max(0, abs(sequence - delivery) - tolerance)


def attribute_values(foundations: list[FoundationInput], attribute: str) -> list[int]:
    return [scaled_attribute(attribute_value(item, attribute)) for item in foundations]


def attribute_span(values: list[int]) -> int:
    if not values:
        return 0
    return max(values) - min(values)


def window_violation(
    values_by_sequence: dict[int, int], positions: list[int], direction: str
) -> int:
    total = 0
    for index, earlier in enumerate(positions):
        for later in positions[index + 1 :]:
            left = values_by_sequence[earlier]
            right = values_by_sequence[later]
            if direction == "ascending":
                total += max(0, left - right)
            else:
                total += max(0, right - left)
    return total


def window_pair_count(positions: list[int]) -> int:
    count = len(positions)
    return count * (count - 1) // 2
