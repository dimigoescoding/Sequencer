from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_dataset, owned_project
from apps.datasets.forms import UploadForm
from apps.datasets.services.template import build_template
from apps.datasets.services.uploads import UploadRejected, activate_dataset, create_dataset_version

SORTABLE = {
    "foundation_id",
    "include",
    "weight_t",
    "delivery_sequence",
    "delivery_batch",
    "difficulty_value",
    "punch_through",
    "source_row",
}


@login_required
def dataset_index(request, project_id: int):
    project = owned_project(request.user, project_id)
    form = UploadForm()
    dataset = project.active_dataset
    return render(
        request,
        "datasets/index.html",
        {
            "project": project,
            "form": form,
            "versions": project.dataset_versions.all(),
            "dataset": dataset,
            "page_obj": _foundation_page(request, dataset),
            "issues": dataset.issues.all() if dataset else [],
        },
    )


@login_required
def dataset_upload(request, project_id: int):
    project = owned_project(request.user, project_id)
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["workbook"]
        try:
            version = create_dataset_version(
                project=project,
                user=request.user,
                filename=upload.name,
                content=upload.read(),
            )
        except UploadRejected as exc:
            form.add_error("workbook", str(exc))
        else:
            if version.error_count:
                messages.error(
                    request,
                    "The workbook was stored, but critical errors block activation and optimisation.",
                )
            elif version.warning_count:
                messages.warning(
                    request,
                    "The workbook was stored with warnings. Warnings do not block optimisation.",
                )
            else:
                messages.success(request, "Dataset version stored.")
            return redirect("datasets:version", project_id=project.pk, version_id=version.pk)
    return render(request, "datasets/upload.html", {"project": project, "form": form})


@login_required
def dataset_template(request, project_id: int):
    owned_project(request.user, project_id)
    response = HttpResponse(
        build_template(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="Foundation_Input_template.xlsx"'
    return response


@login_required
def dataset_version(request, project_id: int, version_id: int):
    project = owned_project(request.user, project_id)
    version = owned_dataset(request.user, project_id, version_id)
    return render(
        request,
        "datasets/version.html",
        {
            "project": project,
            "dataset": version,
            "page_obj": _foundation_page(request, version),
            "issues": version.issues.all(),
            "scenarios": project.scenarios.select_related("vessel_settings"),
        },
    )


@login_required
@require_POST
def dataset_activate(request, project_id: int, version_id: int):
    version = owned_dataset(request.user, project_id, version_id)
    if not version.can_activate:
        messages.error(request, "Resolve critical errors before activating this dataset.")
        return redirect("datasets:version", project_id=project_id, version_id=version.pk)
    activate_dataset(version)
    messages.success(request, f"Dataset version {version.version_number} is now active.")
    return redirect("datasets:index", project_id=project_id)


@login_required
def dataset_original(request, project_id: int, version_id: int):
    version = owned_dataset(request.user, project_id, version_id)
    if not version.original_file:
        raise Http404("The original workbook is not available.")
    try:
        handle = version.original_file.open("rb")
    except (FileNotFoundError, OSError) as exc:
        raise Http404("The original workbook is no longer on disk.") from exc
    return FileResponse(
        handle, as_attachment=True, filename=version.original_filename or "Foundation_Input.xlsx"
    )


def _foundation_page(request, dataset):
    if dataset is None:
        return None
    rows = dataset.foundations.all()
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(foundation_id__icontains=query)
    include = request.GET.get("include", "")
    if include == "yes":
        rows = rows.filter(include=True)
    elif include == "no":
        rows = rows.filter(include=False)
    sort = request.GET.get("sort", "source_row")
    if sort not in SORTABLE:
        sort = "source_row"
    if request.GET.get("dir") == "desc":
        sort = f"-{sort}"
    rows = rows.order_by(sort, "id")
    return Paginator(rows, 25).get_page(request.GET.get("page"))
