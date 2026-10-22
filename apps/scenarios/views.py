from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_project, owned_scenario
from apps.datasets.services.catalogue import setting_key
from apps.optimisation.services.runner import SolveBlocked, SolveBusy, blocking_messages, execute
from apps.projects.services import duplicate_scenario
from apps.scenarios.forms import ScenarioForm, WorkbookSettingsForm
from apps.scenarios.models import VesselSettings
from apps.scenarios.services.sync import sync_scenario_from_dataset


@login_required
def scenario_list(request, project_id: int):
    project = owned_project(request.user, project_id)
    scenarios = project.scenarios.select_related("dataset_version", "vessel_settings")
    return render(request, "scenarios/list.html", {"project": project, "scenarios": scenarios})


@login_required
def scenario_create(request, project_id: int):
    project = owned_project(request.user, project_id)
    initial = {}
    if project.active_dataset and project.active_dataset.error_count == 0:
        initial["dataset_version"] = project.active_dataset.pk
    form = ScenarioForm(
        project, request.POST or None, initial=None if request.method == "POST" else initial
    )
    if request.method == "POST" and form.is_valid():
        scenario = form.save(commit=False)
        scenario.project = project
        scenario.save()
        VesselSettings.objects.create(scenario=scenario)
        sync_scenario_from_dataset(scenario)
        messages.success(
            request,
            "Scenario created. Constraints and settings were loaded from the selected workbook.",
        )
        return redirect(scenario)
    return render(
        request, "scenarios/form.html", {"project": project, "form": form, "title": "New scenario"}
    )


@login_required
def scenario_detail(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    return render(
        request,
        "scenarios/detail.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "constraints": scenario.constraints.all(),
            "runs": scenario.runs.all()[:8],
        },
    )


@login_required
def scenario_edit(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    previous_dataset = scenario.dataset_version_id
    form = ScenarioForm(scenario.project, request.POST or None, instance=scenario)
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        if updated.dataset_version_id != previous_dataset:
            sync_scenario_from_dataset(updated)
        messages.success(request, "Scenario updated.")
        return redirect(scenario)
    return render(
        request,
        "scenarios/form.html",
        {"project": scenario.project, "scenario": scenario, "form": form, "title": "Edit scenario"},
    )


@login_required
@require_POST
def scenario_duplicate(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    clone = duplicate_scenario(scenario)
    messages.success(
        request, "Scenario duplicated. Change its constraints without affecting the original."
    )
    return redirect(clone)


@login_required
@require_POST
def scenario_delete(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    project_id = scenario.project_id
    scenario.delete()
    messages.success(request, "Scenario deleted.")
    return redirect("scenarios:list", project_id=project_id)


@login_required
def vessel_settings(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    dataset = scenario.dataset_version
    definitions = []
    if dataset is not None:
        stored = scenario.vessel_settings.workbook_values or {}
        definitions = [
            (item.name, stored.get(item.name, item.value)) for item in dataset.setting_rows.all()
        ]
    form = WorkbookSettingsForm(
        definitions,
        request.POST or None,
        initial={"solver_time_limit_seconds": scenario.vessel_settings.solver_time_limit_seconds},
    )
    if request.method == "POST" and form.is_valid():
        settings = scenario.vessel_settings
        if definitions:
            values = form.value_map()
            settings.workbook_values = values
            for name, raw in values.items():
                if setting_key(name) == "mp_per_trip":
                    settings.max_foundations_per_trip = int(Decimal(raw))
        settings.solver_time_limit_seconds = form.cleaned_data["solver_time_limit_seconds"]
        settings.save()
        messages.success(request, "Settings saved.")
        return redirect(scenario)
    return render(
        request,
        "scenarios/settings.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "form": form,
            "definitions": definitions,
        },
    )


@login_required
def generate(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    conflicts = blocking_messages(scenario)
    if request.method == "POST":
        if conflicts:
            messages.error(request, "The solver was not started. Resolve the conflicts below.")
        else:
            try:
                run = execute(scenario)
            except SolveBlocked as exc:
                conflicts = exc.conflicts
                messages.error(request, "The solver was not started.")
            except SolveBusy:
                messages.error(
                    request,
                    "A sequence is already running on this server. Wait for it to finish, then try again.",
                )
            else:
                if run.status == "INFEASIBLE":
                    messages.error(
                        request, "No feasible sequence exists. Hard constraints were not relaxed."
                    )
                elif run.status == "INVALID":
                    messages.error(
                        request, "The result failed independent validation and is not approved."
                    )
                elif run.status in {"OPTIMAL", "FEASIBLE"}:
                    messages.success(
                        request, f"Sequence stored with solver status {run.solver_status}."
                    )
                else:
                    messages.warning(request, run.message)
                return redirect("optimisation:detail", run_id=run.pk)
    return render(
        request,
        "scenarios/generate.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "conflicts": conflicts,
            "constraints": scenario.constraints.filter(active=True),
        },
    )


@login_required
def scenario_runs(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    return render(
        request,
        "scenarios/runs.html",
        {"project": scenario.project, "scenario": scenario, "runs": scenario.runs.all()},
    )
