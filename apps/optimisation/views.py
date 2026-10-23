from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render

from apps.access import owned_run
from apps.exports.services.workbook import build_run_workbook, export_filename
from apps.optimisation.services.timelapse import timelapse_payload

SEQUENCE_SORTS = {
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
    sort = request.GET.get("sort", "installation_sequence")
    if sort not in SEQUENCE_SORTS:
        sort = "installation_sequence"
    if request.GET.get("dir") == "desc":
        sort = f"-{sort}"
    rows = rows.order_by(sort, "id")
    tab = request.GET.get("tab", "sequence")
    return render(
        request,
        "optimisation/run.html",
        {
            "project": run.scenario.project,
            "scenario": run.scenario,
            "run": run,
            "page_obj": Paginator(rows, 25).get_page(request.GET.get("page")),
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
