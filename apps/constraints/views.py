from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_constraint, owned_scenario
from apps.constraints.forms import ConstraintForm, ConstraintLevelForm
from apps.constraints.library import CONSTRAINT_TYPES, TYPE_ORDER
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
            "constraints": scenario.constraints.all(),
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
    form = _form(request, constraint_type, foundations, vessel, columns)
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
    form = ConstraintLevelForm(
        request.POST or None,
        initial={"enforcement": constraint.enforcement, "severity": constraint.severity},
    )
    if request.method == "POST" and form.is_valid():
        constraint.enforcement = form.cleaned_data["enforcement"]
        constraint.severity = form.cleaned_data["severity"]
        constraint.save(update_fields=["enforcement", "severity", "updated_at"])
        messages.success(request, "Constraint type and severity updated.")
        return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)
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
    request, constraint_type, foundations, vessel, columns, instance: Constraint | None = None
):
    included_ids = [item.foundation_id for item in foundations if item.include]
    initial = None
    initial_parameters = None
    if instance is not None and request.method != "POST":
        initial = {
            "name": instance.name,
            "description": instance.description,
            "enforcement": instance.enforcement,
            "severity": instance.severity,
            "active": instance.active,
        }
        initial_parameters = instance.parameters_json
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
