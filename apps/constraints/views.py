from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.access import owned_constraint, owned_scenario


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
@require_POST
def constraint_toggle(request, project_id: int, scenario_id: int, constraint_id: int):
    constraint = owned_constraint(request.user, project_id, scenario_id, constraint_id)
    constraint.active = not constraint.active
    constraint.save(update_fields=["active", "updated_at"])
    messages.success(
        request, "Constraint activated." if constraint.active else "Constraint deactivated."
    )
    return redirect("constraints:list", project_id=project_id, scenario_id=scenario_id)
