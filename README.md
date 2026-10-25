# Sequencer

Sequencer is a browser application for defining an optimised installation sequence for offshore wind foundations. MVP 1 supports one package: foundation installation.

A user creates projects, uploads a foundation workbook, validates it, configures vessel trip settings, and enters hard and soft sequencing constraints. The application builds a Google OR-Tools CP-SAT model from those records, stores the sequence, checks it with an independent validator, and exports an audit workbook. Sequencer does not invent, recommend, or relax constraints.

## MVP scope

Included:

- Foundation package only
- Multiple projects owned by one user
- Excel upload, template, and validation
- Vessel and trip settings
- User-defined hard and soft constraints, with severity 1–100 on soft constraints
- CP-SAT optimisation, saved scenarios, and saved runs
- Installation sequence, trip summary, and independent validation
- Excel export
- Django login, logout, and password change
- PostgreSQL on Render, SQLite for local development
- Automated tests

Not included: maps, other installation packages, dates, weather, cost, Monte Carlo, Gantt charts, PDF reports, AI or natural-language constraints, executable formulas, multiple vessels at once, real-time collaboration, and registration.

## Technology

- Python 3.12, Django 5.2, Django templates, Bootstrap 5
- pandas and openpyxl
- Google OR-Tools CP-SAT
- PostgreSQL in production, SQLite locally
- Gunicorn and WhiteNoise
- pytest and Ruff

## Local installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in. Local settings use `sequencer.settings.local`, which enables `DEBUG` and SQLite unless `DATABASE_URL` is set.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `sequencer.settings.local` or `sequencer.settings.production` |
| `SECRET_KEY` | Required in production. Local settings supply an insecure default. |
| `DEBUG` | `true` locally. Production settings force this off. |
| `ALLOWED_HOSTS` | Comma-separated hosts. |
| `DATABASE_URL` | `sqlite:///db.sqlite3` locally, or a PostgreSQL URL. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated `https://` origins. |
| `RENDER_EXTERNAL_URL` | Set by Render. Added to hosts and CSRF origins. |
| `SECURE_SSL_REDIRECT` | Production default `true`. |
| `MEDIA_ROOT` | Upload directory. Render blueprint uses `/var/data/media`. |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | Used only by `createsuperuser --noinput`. Do not commit them. |

## Database setup

Local SQLite is created by `migrate` at `db.sqlite3`. For a local PostgreSQL database, set `DATABASE_URL` and run migrations again:

```bash
python manage.py migrate
```

## Creating a superuser

There is no registration page. Create an administrator from the shell:

```bash
python manage.py createsuperuser
```

Or, with the three `DJANGO_SUPERUSER_*` variables set in the environment:

```bash
python manage.py createsuperuser --noinput
```

The admin index is `/admin/`.

## Demo data

Local only. The command refuses to run when `DEBUG` is off, so it cannot create a production login.

```bash
python manage.py seed_demo
```

- Username: `demo`
- Password: `demo-local-only`
- Project: `Demo Foundation Project`
- Scenario: `Demonstration`
- Dataset: 12 synthetic foundations, one excluded

Generate and export that scenario:

```bash
python manage.py solve_scenario \
  --project "Demo Foundation Project" \
  --scenario "Demonstration" \
  --username demo \
  --export /tmp/sequencer-demo.xlsx
```

## Tests and lint

```bash
pytest
ruff check .
ruff format --check .
```

Production deployment checks, from a shell that does not reuse the insecure local secret:

```bash
DJANGO_SETTINGS_MODULE=sequencer.settings.production \
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
ALLOWED_HOSTS=localhost \
DATABASE_URL=sqlite:///db.sqlite3 \
SECURE_SSL_REDIRECT=true \
python manage.py check --deploy
```

## Excel input

Download `Foundation_Input_template.xlsx` from a project's Foundation Data page. The workbook needs one sheet, `Foundation_Input`.

Mandatory columns: `Foundation_ID`, `Include`, `Weight_t`, `Delivery_Sequence`.

Optional columns: `Length_m`, `Delivery_Batch`, `Easting_m`, `Northing_m`, `Punch_Through`, `Difficulty_Value`, `Eccentricity_Limit_m`, `Fixed_Trip`, `Fixed_Position`, `Earliest_Sequence`, `Latest_Sequence`, `Notes`.

`Foundation_ID` must be unique. `Include` and `Punch_Through` accept Yes/No, True/False, or 1/0. `Weight_t` must be positive. Sequence fields must be positive integers when present, and earliest cannot exceed latest. Empty optional cells stay null. Formulas and macro-enabled workbooks are rejected and are not executed.

Critical errors block activation and optimisation. Warnings, such as missing coordinates, do not. `Fixed_Trip`, `Fixed_Position`, `Earliest_Sequence`, and `Latest_Sequence` in the sheet are stored data. They are not turned into constraints unless you add those constraints yourself. A `Fixed_Position` above the scenario capacity is reported before the solver starts.

Uploads are limited to `.xlsx` files of at most 10 MB.

## Supported constraint types

Each constraint is a database record with enforcement `hard` or `soft`. Soft constraints require a severity from 1 to 100. Hard constraints do not use severity and are never converted to soft.

- Maximum trip payload
- Fixed trip
- Fixed vessel position
- Allowed vessel positions by attribute
- Excluded vessel positions by attribute
- Earliest sequence position
- Latest sequence position
- Precedence
- Maximum matching foundations per trip
- Minimum matching foundations per trip
- Same-trip grouping
- Separate-trip rule
- Attribute ordering
- Delivery-sequence alignment
- Difficulty progression
- Minimise within-trip distance

Attribute rules use a fixed operator list (`equals`, `does_not_equal`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `between`, `in_list`, `not_in_list`, `is_blank`, `is_not_blank`) against columns in the uploaded dataset. The rule builder does not accept free-text logic or code.

Distance, difficulty progression, and delivery alignment stay unavailable until the required columns are complete. The constraint list explains why.

## Starting the app

```bash
python manage.py runserver
```

Sign in, create a project, upload a workbook, activate a valid dataset, create a scenario, set vessel limits, add constraints, and generate a sequence. Results are under the scenario's Results tab and can be exported to Excel.

## Render deployment

`render.yaml` defines a Python web service and a PostgreSQL 16 database.

1. Push this repository to GitHub.
2. In Render, create a Blueprint from `render.yaml`, or create the web service and database by hand using the same commands.
3. Confirm `SECRET_KEY` is generated by Render and is not in git.
4. The build command is `./build.sh`: install dependencies, `collectstatic`, and `migrate`.
5. The start command is Gunicorn with a 180 second timeout so a 120 second solve can finish.
6. Health check path: `/accounts/login/`.
7. Create the first user with a Render shell: `python manage.py createsuperuser`.

Uploaded files use Django's storage API (`FileField` and `default_storage`). The blueprint mounts a 1 GB disk at `/var/data` and sets `MEDIA_ROOT=/var/data/media`. That disk is tied to the service. Replacing the service, or running without the disk, loses uploaded workbooks. Optimisation results and exports are stored in PostgreSQL and can be exported again. Object storage can replace `STORAGES["default"]` later without changing the parser, solver, or export services.

## Known MVP limitations

- One package, one vessel, and no simultaneous vessels.
- No dates, weather, cost, maps, Gantt charts, or PDF reports.
- No user registration or email verification.
- At most 100 included foundations per solve. Within-trip distance is modelled for at most 30.
- Solver time is limited to 1–120 seconds. A feasible result inside the limit is labelled `FEASIBLE`, not `OPTIMAL`, unless OR-Tools proves optimality.
- A hard "minimise distance" constraint has no numeric distance cap. It is a primary objective term. The validator reports it as information, not a pass/fail limit.
- A soft payload limit can return an overloaded trip. The interface warns about that, and the excess is a soft trade-off.
- Direct conflicts are blocked before the solver. Indirect conflicts become `INFEASIBLE` with no sequence. Nothing is relaxed automatically.
- Spreadsheet `Fixed_*` columns are inputs, not automatic constraints.
- The optional reference workbook named in the product specification was not in this repository. No project-specific limits were copied from it.

## Verification recorded for this repository

`python manage.py check --deploy` was run with production settings, a generated `SECRET_KEY`, `ALLOWED_HOSTS=localhost`, SQLite, and `SECURE_SSL_REDIRECT=true`. It finished with exit code 0 and one warning, `security.W021`, because `SECURE_HSTS_PRELOAD` is intentionally false.

These commands were run in this workspace after implementation:

```text
.venv/bin/python manage.py migrate
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py solve_scenario --project "Demo Foundation Project" --scenario "Demonstration" --username demo --export /tmp/sequencer-demo.xlsx
```

The demo solve returned solver status `OPTIMAL` and validation status `Passed`. The export contained `Optimized_Sequence`, `Trip_Summary`, `Validation`, `Foundation_Input`, `Vessel_Settings`, `Constraint_Configuration`, and `Run_Summary`. An infeasible hard payload case is covered by `tests/test_optimisation.py::test_infeasible_run_is_stored_without_a_fabricated_sequence`: the run is `INFEASIBLE`, the sequence is empty, and the hard constraint stays hard.

Further reading: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/OPTIMISATION_METHOD.md](docs/OPTIMISATION_METHOD.md), [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
