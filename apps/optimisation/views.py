from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, When
from django.http import HttpResponse
from django.shortcuts import render

from apps.access import owned_run
from apps.exports.services.workbook import build_run_workbook, export_filename
from apps.optimisation.services.buffer import buffer_column, programme_inputs
from apps.optimisation.services.timelapse import timelapse_payload

SEQUENCE_SORTS = {
    "package",
    "installation_sequence",
    "trip",
    "vessel_position",
    "foundation_id",
    "weight_t",
    "delivery_sequence",
    "sequence_deviation",
    "difficulty_value",
    "soft_penalty",
}


@login_required
def run_detail(request, run_id: int):
    run = owned_run(request.user, run_id)
    rows = run.sequence_rows.all()
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(foundation_id__icontains=query)
    package_order = Case(
        When(package="FOU", then=0),
        When(package="", then=0),
        When(package="IAC", then=1),
        When(package="WTG", then=2),
        default=3,
        output_field=IntegerField(),
    )
    sort = request.GET.get("sort", "")
    if sort not in SEQUENCE_SORTS:
        rows = rows.order_by(package_order, "installation_sequence", "id")
    else:
        if request.GET.get("dir") == "desc":
            sort = f"-{sort}"
        rows = rows.order_by(sort, package_order, "installation_sequence", "id")
    shown = list(rows)
    labels = buffer_column(run.sequence_rows.all(), *programme_inputs(run.dataset_version))
    for row in shown:
        row.buffer_label = labels.get(row.pk, "—")
    tab = request.GET.get("tab", "sequence")
    return render(
        request,
        "optimisation/run.html",
        {
            "project": run.scenario.project,
            "scenario": run.scenario,
            "run": run,
            "sequence_rows": shown,
            "trips": run.trip_rows.all(),
            "checks": run.validation_rows.all(),
            "tab": tab,
            "timelapse": timelapse_payload(run) if tab == "visual" else None,
            "hard_constraints": [
                item
                for item in run.constraint_snapshot or []
                if item.get("active") and item.get("enforcement") == "hard"
            ],
        },
    )


@login_required
def run_export(request, run_id: int):
    run = owned_run(request.user, run_id)
    payload = build_run_workbook(run)
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{export_filename(run)}"'
    return response
