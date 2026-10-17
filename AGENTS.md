# Instructions for future Cursor work

Sequencer MVP 1 is a Django application that sequences offshore wind foundation installation. Keep the following rules in every change.

- Preserve the separation between views, models, and services. Excel parsing, dataset validation, constraint validation, solver-model construction, optimisation, independent result validation, and Excel export stay in the service layer.
- Do not hard-code project-specific engineering constraints, payloads, harbours, difficulty methods, coordinates, or sequences.
- Do not introduce AI-generated constraint logic, natural-language interpretation, or recommendations. The user defines every constraint and its severity.
- Do not relax hard constraints automatically, and do not convert a hard constraint into a soft one.
- Every solver result must be independently validated. If a hard check fails, mark the run invalid and do not present it as an approved sequence.
- Do not fabricate a sequence when the solver is infeasible, unknown, or in error.
- Never execute formulas, macros, or code from uploaded files or from constraint parameters.
- Update tests and documentation when functionality changes.
- Keep the MVP boundaries unless the product specification is deliberately revised. Do not add maps, other packages, weather, cost, Gantt charts, PDF reports, registration, or multi-vessel planning in passing.
- Prefer complete, tested changes over isolated snippets. Run `pytest` and `ruff check .` before considering a change finished.
