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

When a within-trip distance constraint is active, total within-trip distance is part of the CP-SAT objective. The same search chooses which locations share a trip and the order of those locations. The route is not rearranged after the trips have been fixed. A feasible assignment found without the distance term is given to the search as a starting hint. The search may still move a location into another trip.

## Hard constraints

Hard constraints are added with `model.Add`. They are never rewritten as penalties.

| Type | Model |
| --- | --- |
| Maximum trip payload | Sum of weight on each trip is at most `maximum_payload_t`. |
| Fixed trip | The foundation occupies a position in that trip. |
| Fixed vessel position | The foundation occupies that position, and that trip when a trip is supplied. |
| Allowed or excluded positions | Matching foundations may only use the permitted positions. |
| Earliest trip | One location, or locations matching an attribute, cannot be installed before trip T. `position_of` is at least `(T - 1) * N + 1`. Trip 2 keeps them out of the first trip. |
| Latest sequence | `position_of` is at most a sequence index, or at most the end of a named trip. |
| Precedence | Successor position minus predecessor position is at least `minimum_gap`, and at most `maximum_gap` when set. A gap of 1 means the successor is strictly later. |
| Maximum or minimum count | Matching foundations per applicable trip stay inside the count. |
| Same trip or separate trip | `trip_of` is equal, or pairwise unequal. |
| Attribute ordering, delivery alignment, difficulty progression | The measured violation must be zero. |
| Minimise within-trip distance | The objective includes the sum of Euclidean legs between consecutive positions in the same trip, plus harbour legs when enabled. A hard term is weighted ahead of soft penalties. A soft term is scaled by severity. There is no numeric distance cap. The validator reports the metres as information. |

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

The objective is the sum of these scaled terms and any within-trip distance term. A hard distance term is the total metres multiplied by a weight large enough that one metre outranks every soft penalty. A soft distance term is scaled from metres with the formula above. The stored objective is that integer, not a physical cost.

## Objective construction

CP-SAT minimises the sum. `num_search_workers` is 1 and `random_seed` is 1 (`SOLVER_SEED`), so repeated runs with the same data and settings follow the same search. A change to settings, constraints, or the time limit can change a feasible-but-not-optimal result.

The time limit is the scenario's `solver_time_limit_seconds`, chosen on the settings page from 1 to 600 seconds.

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

- MVP 1 solves at most 60 included foundations, including within-trip distance. The supplied workbook has 50 locations. The Render Free instance has 512 MB of RAM and 0.1 CPU. The solver time limit is capped at 600 seconds. A run that stops at the time limit is `FEASIBLE` or `UNKNOWN`, not a fabricated optimum.

Workbook severities on a 0–1 scale are mapped onto 1–100 before the penalty (0.5 becomes 50). Hard rows use `NA` and have no severity. These named workbook rules are applied as written; the explanation cell is stored and is not parsed:

- `Spider locations FOU`: matching spider locations occupy the first positions, in any order.
- `Shallow locations`: at most one matching shallow location on a trip.
- `Infield sailing optimization FOU`: minimise straight-line distance from Easting and Northing inside trips, choosing trip membership and order together, without harbour legs.
- `Jacking difficulty`: soft preference to keep difficult locations out of the first three trips.
- Payload, harbour coordinates, and transit speed have no engineering default. Distance harbour legs stay unavailable until coordinates are entered on the constraint or the vessel settings.
- Transit speed is stored for the scenario record. MVP 1 does not convert distance into time.
- Two-foundation hard precedence cycles are rejected before the solver. Longer cycles are left for CP-SAT and return `INFEASIBLE` when they cannot be satisfied.
- Soft payload limits intentionally allow overload. The penalty is the excess weight, scaled as above.
- The objective is not a monetary or nautical cost. Compare it only within the same dataset, constraint set, and scaling rules.
