# Instructions for future Cursor work

Sequencer MVP 1 is a Django application that sequences offshore wind foundation installation. Keep the following rules in every change.

- Preserve the separation between views, models, and services. Excel parsing, dataset validation, constraint validation, solver-model construction, optimisation, independent result validation, and Excel export stay in the service layer.
- Do not hard-code project-specific engineering constraints, payloads, harbours, difficulty methods, coordinates, or sequences.
- Do not introduce AI-generated constraint logic, natural-language interpretation, or recommendations. The workbook supplies the starting constraints and settings by name. The user may change hard or soft, set severity, activate or deactivate a constraint, and add a constraint from the supported library. The user may change workbook setting values and select the solver time from 1 to 30 seconds. Do not turn explanation text into a rule, and do not add a setting that is not in the workbook.
- Do not relax hard constraints automatically, and do not convert a hard constraint into a soft one.
- Every solver result must be independently validated. If a hard check fails, mark the run invalid and do not present it as an approved sequence.
- Do not fabricate a sequence when the solver is infeasible, unknown, or in error.
- Never execute formulas, macros, or code from uploaded files or from constraint parameters.
- Update tests and documentation when functionality changes.
- Keep the MVP boundaries unless the product specification is deliberately revised. Do not add maps, other packages, weather, cost, Gantt charts, PDF reports, registration, or multi-vessel planning in passing.
- Keep the Render Free deployment inside one web service and one Postgres database. Do not add a persistent disk, a second worker, a solver limit above 30 seconds, or a shell-only setup step. Original uploads stay behind Django's storage API.
- Prefer complete, tested changes over isolated snippets. Run `pytest` and `ruff check .` before considering a change finished.
