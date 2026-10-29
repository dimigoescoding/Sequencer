from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_project
from apps.constraints.library import CONSTRAINT_TYPES, TYPE_ORDER
from apps.optimisation.models import OptimisationRun
from apps.projects.forms import ProjectForm
from apps.projects.models import Project
from apps.projects.services import archive_project, duplicate_project, restore_project


@login_required
def project_list(request):
    projects = Project.objects.filter(owner=request.user, status=Project.Status.ACTIVE)
    return render(request, "projects/list.html", {"projects": projects, "archived": False})


@login_required
def archived_list(request):
    projects = Project.objects.filter(owner=request.user, status=Project.Status.ARCHIVED)
    return render(request, "projects/list.html", {"projects": projects, "archived": True})


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.owner = request.user
        project.package_type = Project.PackageType.FOUNDATION
        project.save()
        messages.success(request, "Project created.")
        return redirect(project)
    return render(request, "projects/form.html", {"form": form, "title": "New project"})


@login_required
def project_detail(request, project_id: int):
    project = owned_project(request.user, project_id)
    scenarios = project.scenarios.select_related("dataset_version", "vessel_settings")
    runs = OptimisationRun.objects.filter(scenario__project=project).select_related("scenario")[:8]
    return render(
        request,
        "projects/detail.html",
        {
            "project": project,
            "scenarios": scenarios,
            "runs": runs,
            "dataset": project.active_dataset,
        },
    )


@login_required
def project_edit(request, project_id: int):
    project = owned_project(request.user, project_id)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Project renamed.")
        return redirect(project)
    return render(
        request, "projects/form.html", {"form": form, "project": project, "title": "Rename project"}
    )


@login_required
@require_POST
def project_duplicate(request, project_id: int):
    project = owned_project(request.user, project_id)
    clone = duplicate_project(project)
    messages.success(request, "Project duplicated. Optimisation runs were not copied.")
    return redirect(clone)


@login_required
@require_POST
def project_archive(request, project_id: int):
    project = owned_project(request.user, project_id)
    archive_project(project)
    messages.success(request, "Project archived.")
    return redirect("projects:archived")


@login_required
@require_POST
def project_restore(request, project_id: int):
    project = owned_project(request.user, project_id)
    restore_project(project)
    messages.success(request, "Project restored.")
    return redirect(project)


@login_required
def project_vessel(request, project_id: int):
    project = owned_project(request.user, project_id)
    scenarios = project.scenarios.select_related("vessel_settings")
    return render(request, "projects/vessel.html", {"project": project, "scenarios": scenarios})


@login_required
def project_help(request, project_id: int):
    project = owned_project(request.user, project_id)
    library = [
        {"label": CONSTRAINT_TYPES[key]["label"], "summary": CONSTRAINT_TYPES[key]["summary"]}
        for key in TYPE_ORDER
    ]
    return render(request, "projects/help.html", {"project": project, "library": library})


@login_required
def project_runs(request, project_id: int):
    project = owned_project(request.user, project_id)
    runs = OptimisationRun.objects.filter(scenario__project=project).select_related(
        "scenario", "dataset_version"
    )
    return render(request, "projects/runs.html", {"project": project, "runs": runs})


def project_or_404(user, project_id: int) -> Project:
    return get_object_or_404(Project, pk=project_id, owner=user)
