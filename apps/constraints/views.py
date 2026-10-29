from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_constraint, owned_scenario
from apps.constraints.forms import ConstraintForm, ConstraintLevelForm
from apps.constraints.library import CONSTRAINT_TYPES, TYPE_ORDER, display_constraints
from apps.constraints.models import Constraint
from apps.constraints.services.availability import availability_reasons, punch_through_explanation
from apps.optimisation.services.runner import scenario_context, vessel_config


@login_required
def constraint_list(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    return render(
        request,
        "constraints/list.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "constraints": display_constraints(scenario.constraints.all()),
        },
    )


@login_required
def constraint_choose(request, project_id: int, scenario_id: int):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    foundations, _vessel, _constraints, columns = scenario_context(scenario)
    reasons = availability_reasons(foundations, columns, vessel_config(scenario.vessel_settings))
    library = [
        {
            "key": key,
            "label": CONSTRAINT_TYPES[key]["label"],
            "summary": CONSTRAINT_TYPES[key]["summary"],
            "reason": reasons.get(key, ""),
        }
        for key in TYPE_ORDER
    ]
    return render(
        request,
        "constraints/choose.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "library": library,
            "punch_message": punch_through_explanation(foundations, columns),
            "has_dataset": scenario.dataset_version_id is not None
            and scenario.dataset_version.error_count == 0,
        },
    )


@login_required
def constraint_create(request, project_id: int, scenario_id: int, constraint_type: str):
    scenario = owned_scenario(request.user, project_id, scenario_id)
    if constraint_type not in CONSTRAINT_TYPES:
        messages.error(request, "That constraint type is not supported.")
        return redirect("constraints:choose", project_id=project_id, scenario_id=scenario_id)
    foundations, vessel, _constraints, columns = scenario_context(scenario)
    reason = availability_reasons(foundations, columns, vessel).get(constraint_type, "")
    if reason:
        messages.error(request, reason)
        return redirect("constraints:choose", project_id=project_id, scenario_id=scenario_id)
    if scenario.dataset_version_id is None or scenario.dataset_version.error_count:
        messages.error(request, "Select a valid dataset before adding constraints.")
        return redirect("constraints:choose", project_id=project_id, scenario_id=scenario_id)
    form = _form(request, scenario, constraint_type, foundations, vessel, columns)
    if request.method == "POST" and form.is_valid():
        order = (scenario.constraints.aggregate(maximum=Max("display_order"))["maximum"] or 0) + 1
        Constraint.objects.create(
            scenario=scenario,
            name=form.cleaned_data["name"],
            constraint_type=constraint_type,
            description=form.cleaned_data["description"],
            active=bool(form.cleaned_data["active"]),
            enforcement=form.cleaned_data["enforcement"],
            severity=form.cleaned_data["severity"],
            scope=form.cleaned_data.get("scope") or "",
            package=form.cleaned_data.get("package") or "FOU",
            parameters_json=form.cleaned_data["parameters"],
            display_order=order,
        )
        messages.success(request, "Constraint added. It will be used only if you leave it active.")
        return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)
    return render(
        request,
        "constraints/form.html",
        _form_context(scenario, constraint_type, form),
    )


@login_required
def constraint_edit(request, project_id: int, scenario_id: int, constraint_id: int):
    constraint = owned_constraint(request.user, project_id, scenario_id, constraint_id)
    scenario = constraint.scenario
    if request.method == "POST" and "name" not in request.POST:
        return _edit_level(request, constraint)
    foundations, vessel, _constraints, columns = scenario_context(scenario)
    form = _form(
        request,
        scenario,
        constraint.constraint_type,
        foundations,
        vessel,
        columns,
        initial={
            "package": constraint.package or "FOU",
            "name": constraint.name,
            "description": constraint.description,
            "enforcement": constraint.enforcement,
            "severity": constraint.severity,
            "active": constraint.active,
        },
        initial_parameters=constraint.parameters_json or {},
    )
    if request.method == "POST" and form.is_valid():
        constraint.name = form.cleaned_data["name"]
        constraint.description = form.cleaned_data["description"]
        constraint.active = bool(form.cleaned_data["active"])
        constraint.enforcement = form.cleaned_data["enforcement"]
        constraint.severity = form.cleaned_data["severity"]
        constraint.scope = form.cleaned_data.get("scope") or ""
        constraint.package = form.cleaned_data.get("package") or "FOU"
        constraint.parameters_json = form.cleaned_data["parameters"]
        constraint.save()
        messages.success(request, "Constraint updated.")
        return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)
    return render(
        request,
        "constraints/form.html",
        _form_context(scenario, constraint.constraint_type, form, constraint),
    )


def _edit_level(request, constraint):
    scenario = constraint.scenario
    package_choices = None
    if constraint.constraint_type == "package_buffer":
        package_choices = [("IAC", "IAC"), ("WTG", "WTG")]
    elif constraint.constraint_type == "loop_id_sequence":
        package_choices = [("IAC", "IAC")]
    elif constraint.constraint_type == "string_id_sequence":
        package_choices = [("WTG", "WTG")]
    form = ConstraintLevelForm(
        request.POST or None,
        package_choices=package_choices,
        initial={
            "package": constraint.package or "FOU",
            "enforcement": constraint.enforcement,
            "severity": constraint.severity,
        },
    )
    if form.is_valid():
        constraint.package = form.cleaned_data["package"]
        constraint.enforcement = form.cleaned_data["enforcement"]
        constraint.severity = form.cleaned_data["severity"]
        constraint.save(update_fields=["package", "enforcement", "severity", "updated_at"])
        messages.success(request, "Constraint type and severity updated.")
        return redirect("constraints:list", project_id=scenario.project_id, scenario_id=scenario.pk)
    return render(
        request,
        "constraints/level.html",
        {
            "project": scenario.project,
            "scenario": scenario,
            "constraint": constraint,
            "form": form,
        },
    )


@login_required
@require_POST
def constraint_copy(request, project_id: int, scenario_id: int, constraint_id: int):
    source = owned_constraint(request.user, project_id, scenario_id, constraint_id)
    scenario = source.scenario
    order = (scenario.constraints.aggregate(maximum=Max("display_order"))["maximum"] or 0) + 1
    Constraint.objects.create(
        scenario=scenario,
        name=_copy_name(source.name),
        constraint_type=source.constraint_type,
        description=source.description,
        active=source.active,
        enforcement=source.enforcement,
        severity=source.severity,
        scope=source.scope,
        package=source.package,
        parameters_json=source.parameters_json,
        display_order=order,
    )
    messages.success(request, "Constraint copied.")
    return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)


def _copy_name(name: str) -> str:
    suffix = " copy"
    trimmed = name.strip() or "Constraint"
    if len(trimmed) + len(suffix) <= 200:
        return trimmed + suffix
    return trimmed[: 200 - len(suffix)].rstrip() + suffix


@login_required
@require_POST
def constraint_toggle(request, project_id: int, scenario_id: int, constraint_id: int):
    constraint = owned_constraint(request.user, project_id, scenario_id, constraint_id)
    constraint.active = not constraint.active
    constraint.save(update_fields=["active", "updated_at"])
    messages.success(
        request, "Constraint activated." if constraint.active else "Constraint deactivated."
    )
    return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)


@login_required
@require_POST
def constraint_delete(request, project_id: int, scenario_id: int, constraint_id: int):
    constraint = owned_constraint(request.user, project_id, scenario_id, constraint_id)
    constraint.delete()
    messages.success(request, "Constraint deleted.")
    return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)


def _form(
    request,
    scenario,
    constraint_type,
    foundations,
    vessel,
    columns,
    initial=None,
    initial_parameters=None,
):
    included_ids = [item.foundation_id for item in foundations if item.include]
    dataset = scenario.dataset_version
    if dataset is not None:
        included_ids.extend(row.cable_id for row in dataset.cables.all() if row.include)
        included_ids.extend(row.wtg_id for row in dataset.wtg_locations.all() if row.include)
    for identity in _referenced_ids(initial_parameters or {}):
        if identity not in included_ids:
            included_ids.append(identity)
    return ConstraintForm(
        data=request.POST or None,
        constraint_type=constraint_type,
        foundation_ids=included_ids,
        columns=sorted(columns),
        foundations=foundations,
        vessel=vessel,
        columns_present=columns,
        initial=initial,
        initial_parameters=initial_parameters,
    )


def _referenced_ids(parameters: dict) -> list[str]:
    found = []
    for key in ("foundation_id", "predecessor_foundation_id", "successor_foundation_id"):
        if parameters.get(key) not in (None, ""):
            found.append(str(parameters[key]))
    for item in parameters.get("foundation_ids") or []:
        found.append(str(item))
    return found


def _form_context(scenario, constraint_type, form, constraint=None):
    return {
        "project": scenario.project,
        "scenario": scenario,
        "form": form,
        "constraint_type": constraint_type,
        "type_label": CONSTRAINT_TYPES[constraint_type]["label"],
        "type_summary": CONSTRAINT_TYPES[constraint_type]["summary"],
        "constraint": constraint,
    }
