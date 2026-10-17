"""Owner lookups. Missing objects and other users' objects both return 404."""

from django.shortcuts import get_object_or_404

from apps.constraints.models import Constraint
from apps.datasets.models import DatasetVersion
from apps.optimisation.models import OptimisationRun
from apps.projects.models import Project
from apps.scenarios.models import Scenario


def owned_project(user, project_id: int) -> Project:
    return get_object_or_404(Project, pk=project_id, owner=user)


def owned_scenario(user, project_id: int, scenario_id: int) -> Scenario:
    return get_object_or_404(
        Scenario.objects.select_related("project", "dataset_version", "vessel_settings"),
        pk=scenario_id,
        project_id=project_id,
        project__owner=user,
    )


def owned_dataset(user, project_id: int, version_id: int) -> DatasetVersion:
    return get_object_or_404(
        DatasetVersion,
        pk=version_id,
        project_id=project_id,
        project__owner=user,
    )


def owned_constraint(user, project_id: int, scenario_id: int, constraint_id: int) -> Constraint:
    return get_object_or_404(
        Constraint.objects.select_related("scenario", "scenario__project"),
        pk=constraint_id,
        scenario_id=scenario_id,
        scenario__project_id=project_id,
        scenario__project__owner=user,
    )


def owned_run(user, run_id: int) -> OptimisationRun:
    return get_object_or_404(
        OptimisationRun.objects.select_related(
            "scenario",
            "scenario__project",
            "scenario__vessel_settings",
            "dataset_version",
        ),
        pk=run_id,
        scenario__project__owner=user,
    )
