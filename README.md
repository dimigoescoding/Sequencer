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
- Installation sequence, trip summary, independent validation, and a Visual tab
- The Visual tab is an equal-scale easting/northing timelapse of the stored sequence. Lines stay inside a trip. Harbour transit and the join from one trip to the next are not drawn.
- Excel export
- Django login, logout, and password change
- PostgreSQL on Render, SQLite for local development
- Automated tests

Not included: geographic map tiles, other installation packages, dates, weather, cost, Monte Carlo, Gantt charts, PDF reports, AI or natural-language constraints, executable formulas, multiple vessels at once, real-time collaboration, and registration.

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
| `MEDIA_ROOT` | Local upload directory. Production stores workbooks in the database instead. |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | Local: `createsuperuser --noinput`. On Render Free, `start.sh` creates this user once if it does not exist. Do not commit them. |

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

Download `Sequencer_input_template.xlsx` from a project's Foundation Data page. The workbook needs four sheets: `FOU data`, `IAC data`, `WTG data`, and `Programme`. Extra sheets are ignored. Constraints and trip settings are created in the app.

`FOU data` holds one foundation row. Include, WTG ID, Easting, and Northing are required. Average weight is required only when Include is Yes. Spider, shallow, and jacking may be blank. `IAC data` holds one cable per row, joining two location ids. `WTG data` holds one turbine row. `Programme` holds slot numbers and optional P50 start and end times for each package. A slot is not a location id.

On a scenario, the Package dropdown is FOU, IAC, or WTG. FOU per trip and WTG per trip are edited in settings. Solver time, from 1 to 600 seconds, is one limit for the whole programme.

Ids must be unique inside a sheet. Include accepts Yes or No. Macro-enabled workbooks are rejected. Formula text is not calculated. If Excel has stored a calculated value, that stored value is used.

Critical errors block activation and optimisation. Choosing another dataset does not delete the scenario's constraints or trip settings. The solver builds one sequence for the included packages. It does not invent a buffer or a package order. If a hard check fails, the whole run is invalid.

Uploads are limited to `.xlsx` files of at most 2 MB.

## Supported constraint types

Each constraint is a database record with enforcement `hard` or `soft`. Soft constraints require a severity from 1 to 100. Hard constraints do not use severity. You can change that choice on the constraint. The solver does not make the change for you.

- Maximum trip payload
- Fixed trip
- Fixed vessel position
- Allowed vessel positions by attribute
- Excluded vessel positions by attribute
- Earliest trip
- Latest sequence position
- Precedence
- Maximum matching foundations per trip
- Minimum matching foundations per trip
- Same-trip grouping
- Separate-trip rule
- Attribute ordering
- Delivery-sequence alignment
- Difficulty progression
- Minimise total sailing distance
- Matching locations first
- Avoid matches in the first trips

Attribute rules use a fixed operator list (`equals`, `does_not_equal`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `between`, `in_list`, `not_in_list`, `is_blank`, `is_not_blank`) against columns in the uploaded dataset. The rule builder does not accept free-text logic or code.

Distance, difficulty progression, and delivery alignment stay unavailable until the required columns are complete. The constraint list explains why.

## Starting the app

```bash
python manage.py runserver
```

Sign in, create a project, upload a workbook, activate a valid dataset, create a scenario, set vessel limits, add constraints, and generate a sequence. Results are under the scenario's Results tab and can be exported to Excel.

## Render deployment

`render.yaml` is written for the Render Free plan. It creates one Free web service and one Free PostgreSQL 16 database. A workspace can have only one Free database, and that database expires 30 days after creation. Render then allows 14 days to upgrade it before deleting the data. There are no backups on the Free database.

Free web service limits that this configuration respects:

- 512 MB RAM and 0.1 CPU. Gunicorn runs one worker and two threads, so a health check can still be served during a solve. A second solve is refused until the first finishes.
- No persistent disk, and no shell. Local files disappear when the service sleeps, restarts, or redeploys. Original workbooks are stored in Postgres through Django's storage API. Exports are built from database rows.
- The service sleeps after 15 minutes without a request and takes about a minute to wake. Sleeping does not consume the 750 Free instance hours granted per workspace each month.
- The solver time limit is 1–600 seconds. Gunicorn waits up to 660 seconds so that run can finish. A result found before a proof is `FEASIBLE`, not `OPTIMAL`.
- At most 60 included foundations per solve, including total sailing distance. Larger models are rejected before CP-SAT starts.
- Workbooks are limited to 2 MB so a few uploads cannot fill the 1 GB database.

Steps:

1. Push this repository to GitHub.
2. In Render, create a Blueprint from `render.yaml`.
3. Leave `SECRET_KEY` as the generated value. Do not commit it.
4. In the web service environment, set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD`. The start command creates that user once and does not reset the password after that.
5. The build command is `./build.sh`: install dependencies, `collectstatic`, and `migrate`.
6. The start command is `./start.sh`: migrate, create the administrator if needed, then Gunicorn.
7. Health check path: `/healthz/`.
8. Open the `onrender.com` URL. The first request after idle shows Render's wake-up page, then the login page.

Do not add a second Free web service in the same workspace if you want the full monthly hour allowance available for Sequencer. Do not point the app at a database outside Render; Free services that generate a high volume of public outbound traffic can be suspended.

## Known MVP limitations

- One package, one vessel, and no simultaneous vessels.
- No dates, weather, cost, geographic map tiles, Gantt charts, or PDF reports. The Visual tab plots stored easting and northing only.
- No user registration or email verification.
- At most 60 included foundations per solve, including total sailing distance.
- Solver time is limited to 1–600 seconds. A feasible result inside the limit is labelled `FEASIBLE`, not `OPTIMAL`, unless OR-Tools proves optimality.
- The hosted database on the Free plan expires 30 days after creation. Upgrade it before the grace period ends if the data should be kept.
- An active distance constraint minimises total sailing distance: every foundation-to-foundation leg, including the leg that joins one trip to the next. For larger sets the search re-solves stretches of the sequence, including stretches that cross a trip boundary. Harbour transit is not included. It has no numeric distance cap. The validator reports within-trip, trip-to-trip, and total distance in nautical miles.
- A soft payload limit can return an overloaded trip. The interface warns about that, and the excess is a soft trade-off.
- Direct conflicts are blocked before the solver. Indirect conflicts become `INFEASIBLE` with no sequence. Nothing is relaxed automatically.
- Spreadsheet `Fixed_*` columns are inputs, not automatic constraints.
- The optional reference workbook named in the product specification was not in this repository. No project-specific limits were copied from it.

## Verification recorded for this repository

`python manage.py check --deploy` was run with production settings, a generated `SECRET_KEY`, `ALLOWED_HOSTS=localhost`, SQLite, and `SECURE_SSL_REDIRECT=true`. It finished with exit code 0 and one warning, `security.W021`, because `SECURE_HSTS_PRELOAD` is intentionally false.

After the Free-plan changes, `pytest` reported 40 passed and `ruff check .` passed.

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
