# Optimisation method

Sequencer uses Google OR-Tools CP-SAT. The user supplies every constraint. The solver does not add engineering rules and does not drop hard rules that fail.

## Decision variables

For each included foundation and each global sequence position there is a Boolean `x[foundation, position]`. Each included foundation is assigned to exactly one position, and each position receives exactly one foundation.

`position_of[foundation]` is the 1-based sequence index. `trip_of[foundation]` is channelled from that index.

Excluded foundations (`Include` false) are not decision variables and cannot appear in the order.

## Trip and vessel position

With a maximum of `N` foundations per trip:

```text
trip = floor((sequence_position - 1) / N) + 1
vessel_position = ((sequence_position - 1) mod N) + 1
```

The number of trips is `ceil(included_count / N)`. Every trip except the last is full. The last trip is short only when `allow_partial_final_trip` is enabled. If it is disabled and the count is not a multiple of `N`, pre-solver validation blocks the run.

There is no post-processing reorder. The CP-SAT sequence is the installation sequence. Within-trip distance, when requested, is a term inside the same model.

## Hard constraints

Hard constraints are added with `model.Add`. They are never rewritten as penalties.

| Type | Model |
| --- | --- |
| Maximum trip payload | Sum of weight on each trip is at most `maximum_payload_t`. |
| Fixed trip | The foundation occupies a position in that trip. |
| Fixed vessel position | The foundation occupies that position, and that trip when a trip is supplied. |
| Allowed or excluded positions | Matching foundations may only use the permitted positions. |
| Earliest or latest sequence | `position_of` is bounded. An optional trip bound is converted to a sequence index. |
| Precedence | Successor position minus predecessor position is at least `minimum_gap`, and at most `maximum_gap` when set. A gap of 1 means the successor is strictly later. |
| Maximum or minimum count | Matching foundations per applicable trip stay inside the count. |
| Same trip or separate trip | `trip_of` is equal, or pairwise unequal. |
| Attribute ordering, delivery alignment, difficulty progression | The measured violation must be zero. |
| Minimise within-trip distance | There is no numeric distance cap. Total metres are multiplied by `PRIMARY_WEIGHT` (10,000,000) and minimised. One metre outranks any combination of soft penalties. The independent validator reports the distance as information, not a hard pass/fail limit. |

Attribute filters are resolved from the uploaded values before the model is built. They are not decision-dependent expressions, and they are not executable code.

## Soft penalties

A soft constraint introduces a raw integer violation `R` and a dataset-specific upper bound `M`. The objective contribution is an integer `scaled` forced by:

```text
scaled * M >= R * severity * 1000
```

The minimum feasible `scaled` is:

```text
ceil(R * severity * 1000 / M)
```

`scaled_penalty` in `apps/optimisation/services/scaling.py` is the same formula. Each soft constraint is mapped onto 0..1000 according to `R / M`, then multiplied by severity. A severity of 100 is exactly twice a severity of 50 for the same raw ratio and the same `M`.

`M` depends on the constraint type and the current dataset, for example the maximum delivery deviation outside tolerance, the number of ordering pairs, or the total payload. That stops a large unit, such as kilograms or metres, from dominating a count-based preference by accident.

The objective is the sum of these scaled terms, plus the primary distance weight when a hard distance constraint is active. The stored objective is that scaled integer, not a physical cost.

## Objective construction

CP-SAT minimises the sum. `num_search_workers` is 1 and `random_seed` is 1 (`SOLVER_SEED`), so repeated runs with the same data and settings follow the same search. A change to settings, constraints, or the time limit can change a feasible-but-not-optimal result.

The time limit is the scenario's `solver_time_limit_seconds`, chosen on the settings page from 1 to 30 seconds.

## Feasible versus optimal status

| Status | Meaning |
| --- | --- |
| `OPTIMAL` | OR-Tools proved the scaled objective is optimal. |
| `FEASIBLE` | OR-Tools found a feasible solution and stopped, usually at the time limit. It is not labelled optimal. |
| `INFEASIBLE` | The hard model has no solution. The order is empty. |
| `UNKNOWN` | The search stopped without a proof or a solution. The order is empty. |
| `ERROR` | The model could not be solved. The order is empty. |
| Run status `INVALID` | A sequence was returned but independent hard validation failed. `solver_status` stays the OR-Tools status. The run is not approved. |

No status is stored as optimal unless OR-Tools reported `OPTIMAL`. Nothing in the failure path creates a substitute sequence or relaxes a hard constraint.

## Independent validation

After a non-empty order, `evaluate` checks, without using solver state:

- included count, result count, unique IDs, each included foundation once, no excluded foundation
- trip capacity and the partial final trip
- every active hard constraint listed above
- soft metrics, with a non-zero penalty reported as `Soft trade-off`

Overall validation is `Passed` only when no hard check failed. The sequence table records governing constraints and the soft penalty attributed to each foundation. The validation table is the audit record.

## Known limitations

- MVP 1 solves at most 60 included foundations, including within-trip distance. The supplied workbook has 50 locations. The Render Free instance has 512 MB of RAM and 0.1 CPU, and the solver time limit stays capped at 30 seconds. A run that stops at the time limit is `FEASIBLE` or `UNKNOWN`, not a fabricated optimum.

Workbook severities on a 0–1 scale are mapped onto 1–100 before the penalty (0.5 becomes 50). Hard rows use `NA` and have no severity. These named workbook rules are applied as written; the explanation cell is stored and is not parsed:

- `Spider locations FOU`: matching spider locations occupy the first positions, in any order.
- `Shallow locations`: at most one matching shallow location on a trip.
- `Infield sailing optimization FOU`: soft within-trip Euclidean distance from Easting and Northing, without harbour legs.
- `Jacking difficulty`: soft preference to keep difficult locations out of the first three trips.
- Payload, harbour coordinates, and transit speed have no engineering default. Distance harbour legs stay unavailable until coordinates are entered on the constraint or the vessel settings.
- Transit speed is stored for the scenario record. MVP 1 does not convert distance into time.
- Two-foundation hard precedence cycles are rejected before the solver. Longer cycles are left for CP-SAT and return `INFEASIBLE` when they cannot be satisfied.
- Soft payload limits intentionally allow overload. The penalty is the excess weight, scaled as above.
- The objective is not a monetary or nautical cost. Compare it only within the same dataset, constraint set, and scaling rules.
