# Architecture

Sequencer is one Django project. Pages are server-rendered. Business rules live in services that accept plain values, so the solver and validators can be tested without the ORM.

## Application modules

| Module | Responsibility |
| --- | --- |
| `sequencer.settings` | Shared, local, and production settings. Secrets and `DATABASE_URL` come from the environment. |
| `apps.accounts` | Django login, logout, password change, and the account page. No registration. |
| `apps.projects` | Projects, archive/restore, duplication, and the `seed_demo` command. |
| `apps.datasets` | Immutable dataset versions, foundation rows, Excel template, parsing, and upload storage. |
| `apps.scenarios` | Scenarios and vessel settings. |
| `apps.constraints` | Constraint records, the typed rule builder, parameter schemas, and availability checks. |
| `apps.optimisation` | Pre-solver conflicts, CP-SAT model, independent evaluation, run persistence, and `solve_scenario`. |
| `apps.exports` | Audit workbook built from a stored run. |
| `apps.access` | Owner lookups. Another user's object returns 404. |

Views load an owned object, call a service, and render a template. They do not build the CP-SAT model.

## Data flow

1. The user uploads an `.xlsx` file. `create_dataset_version` stores the original bytes through Django's file storage, parses the `Foundation_Input` sheet, and writes `Foundation` and `DatasetIssue` rows. The version is immutable.
2. A version with no critical errors can be activated. A scenario points at one dataset version.
3. Vessel settings and constraint records are edited on that scenario. Parameters are validated by a dedicated form and `validate_parameters`. Nothing in that path uses `eval` or executes spreadsheet formulas.
4. Generate Sequence calls `blocking_messages`. Dataset errors and direct conflicts stop the solver.
5. `solve_order` builds the CP-SAT model and returns a status plus, only for `OPTIMAL` or `FEASIBLE`, an ordered list of foundation IDs.
6. `evaluate` derives trip and vessel position from that order and checks every active hard constraint again. Soft metrics become penalties and trade-offs.
7. `execute` stores the run, sequence rows, trip rows, and validation rows. A hard validation failure sets the run status to `INVALID` and leaves the OR-Tools status unchanged.
8. Excel export reads those stored rows and writes a new workbook. It does not re-solve.

## Model relationships

```text
User
  └── Project
        └── DatasetVersion
              ├── Foundation
              └── DatasetIssue
        └── Scenario
              ├── VesselSettings
              ├── Constraint
              └── OptimisationRun
                    ├── SequenceResult
                    ├── TripResult
                    └── ValidationResult
```

`OptimisationRun.dataset_version` records the dataset that was solved, even if the scenario later points at another version. `parameters_json` holds type-specific constraint parameters only. Foundation rows, settings, and results are columns, not one JSON document.

Indexes cover owner and status, project, scenario, dataset version, foundation ID, and run status.

## Optimisation pipeline

`scenario_context` maps ORM rows to `FoundationInput`, `VesselConfig`, and `ConstraintInput`.

`find_conflicts` checks structural problems and direct contradictions: multiple fixed trips or positions, capacity, payload of foundations already forced onto one trip, grouping versus separation, missing columns, unknown foundations, and two-foundation precedence cycles. It does not call OR-Tools.

`solve_order` assigns each included foundation to one global sequence position. Trip and vessel position are derived from that position and `max_foundations_per_trip`. Excluded foundations are omitted. Hard constraints are model constraints. Soft constraints add scaled penalty variables. The random seed is fixed and one search worker is used.

If OR-Tools returns anything other than optimal or feasible, the order is empty and no sequence rows are written.

## Validation pipeline

`evaluate` does not read solver assertions. It rebuilds placements from the ID list and checks set integrity, trip capacity, the partial-final-trip rule, and each active constraint. The overall status is `Passed` only when every hard check passes. A non-zero soft penalty is `Soft trade-off`, not a failure.

A stored run is approved only when its status is `OPTIMAL` or `FEASIBLE` and validation is `Passed`.

## Export pipeline

`build_run_workbook` writes seven sheets from the run and its dataset: sequence, trip summary, validation, foundation input, vessel settings, constraint configuration, and run summary. Headers are frozen, filters are applied, and hard and soft constraints are coloured differently. The file name is slugified from the project, scenario, and run id.

## File storage

Dataset uploads use `FileField`. Local development stores those files on disk. Production uses `DatabaseStorage`, which writes the bytes to `StoredFile` in Postgres. Render Free cannot keep a disk across sleep or redeploy, and the Free web service has no shell. Export bytes are still generated on download from the sequence tables. Replacing `STORAGES["default"]` with object storage does not require changes to parsing or optimisation.

The Free deployment runs one Gunicorn worker. `execute` holds a process lock so a second solve is refused instead of loading a second CP-SAT model into the 512 MB instance. `/healthz/` does not touch the database.
