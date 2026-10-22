"""Project copy and archive actions."""

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.constraints.models import Constraint
from apps.datasets.models import (
    DatasetConstraint,
    DatasetIssue,
    DatasetSetting,
    DatasetVersion,
    Foundation,
)
from apps.projects.models import Project
from apps.scenarios.models import Scenario, VesselSettings


def duplicate_project(project: Project) -> Project:
    with transaction.atomic():
        clone = Project.objects.create(
            owner=project.owner,
            name=_copy_name(project.name),
            description=project.description,
            package_type=project.package_type,
        )
        version_map: dict[int, DatasetVersion] = {}
        for version in project.dataset_versions.all().order_by("version_number"):
            copied = DatasetVersion.objects.create(
                project=clone,
                version_number=version.version_number,
                original_filename=version.original_filename,
                content_sha256=version.content_sha256,
                is_active=version.is_active,
                row_count=version.row_count,
                included_count=version.included_count,
                error_count=version.error_count,
                warning_count=version.warning_count,
                columns_json=version.columns_json,
                created_by=version.created_by,
            )
            if version.original_file:
                try:
                    version.original_file.open("rb")
                    payload = version.original_file.read()
                    copied.original_file.save(
                        Path(version.original_file.name).name, ContentFile(payload), save=True
                    )
                except (FileNotFoundError, OSError):
                    pass
            Foundation.objects.bulk_create(
                [
                    Foundation(
                        dataset_version=copied,
                        source_row=row.source_row,
                        foundation_id=row.foundation_id,
                        include=row.include,
                        weight_t=row.weight_t,
                        delivery_sequence=row.delivery_sequence,
                        length_m=row.length_m,
                        delivery_batch=row.delivery_batch,
                        easting_m=row.easting_m,
                        northing_m=row.northing_m,
                        punch_through=row.punch_through,
                        difficulty_value=row.difficulty_value,
                        eccentricity_limit_m=row.eccentricity_limit_m,
                        fixed_trip=row.fixed_trip,
                        fixed_position=row.fixed_position,
                        earliest_sequence=row.earliest_sequence,
                        latest_sequence=row.latest_sequence,
                        notes=row.notes,
                        attributes=row.attributes,
                    )
                    for row in version.foundations.all()
                ]
            )
            DatasetIssue.objects.bulk_create(
                [
                    DatasetIssue(
                        dataset_version=copied,
                        severity=issue.severity,
                        code=issue.code,
                        message=issue.message,
                        row_number=issue.row_number,
                        column_name=issue.column_name,
                    )
                    for issue in version.issues.all()
                ]
            )
            DatasetConstraint.objects.bulk_create(
                [
                    DatasetConstraint(
                        dataset_version=copied,
                        package=item.package,
                        name=item.name,
                        explanation=item.explanation,
                        enforcement=item.enforcement,
                        severity=item.severity,
                        reported_severity=item.reported_severity,
                        active=item.active,
                        constraint_type=item.constraint_type,
                        parameters_json=item.parameters_json,
                        source_row=item.source_row,
                        display_order=item.display_order,
                    )
                    for item in version.constraint_rows.all()
                ]
            )
            DatasetSetting.objects.bulk_create(
                [
                    DatasetSetting(
                        dataset_version=copied,
                        name=item.name,
                        key=item.key,
                        value=item.value,
                        source_row=item.source_row,
                    )
                    for item in version.setting_rows.all()
                ]
            )
            version_map[version.pk] = copied
        for scenario in project.scenarios.all():
            _copy_scenario(scenario, clone, version_map)
    return clone


def _copy_scenario(
    scenario: Scenario, project: Project, version_map: dict[int, DatasetVersion]
) -> Scenario:
    dataset = version_map.get(scenario.dataset_version_id) if scenario.dataset_version_id else None
    clone = Scenario.objects.create(
        project=project,
        name=scenario.name,
        description=scenario.description,
        dataset_version=dataset,
        status=scenario.status,
    )
    settings = scenario.vessel_settings
    VesselSettings.objects.create(
        scenario=clone,
        max_foundations_per_trip=settings.max_foundations_per_trip,
        allow_partial_final_trip=settings.allow_partial_final_trip,
        base_maximum_trip_payload_t=settings.base_maximum_trip_payload_t,
        solver_time_limit_seconds=settings.solver_time_limit_seconds,
        transit_speed_knots=settings.transit_speed_knots,
        harbour_easting_m=settings.harbour_easting_m,
        harbour_northing_m=settings.harbour_northing_m,
        workbook_values=settings.workbook_values,
    )
    Constraint.objects.bulk_create(
        [
            Constraint(
                scenario=clone,
                name=item.name,
                constraint_type=item.constraint_type,
                description=item.description,
                active=item.active,
                enforcement=item.enforcement,
                severity=item.severity,
                scope=item.scope,
                parameters_json=item.parameters_json,
                display_order=item.display_order,
            )
            for item in scenario.constraints.all()
        ]
    )
    return clone


def duplicate_scenario(scenario: Scenario) -> Scenario:
    with transaction.atomic():
        clone = _copy_scenario(
            scenario,
            scenario.project,
            {scenario.dataset_version_id: scenario.dataset_version}
            if scenario.dataset_version_id
            else {},
        )
        clone.name = _copy_name(scenario.name)
        clone.save(update_fields=["name", "updated_at"])
    return clone


def archive_project(project: Project) -> None:
    project.status = Project.Status.ARCHIVED
    project.archived_at = timezone.now()
    project.save(update_fields=["status", "archived_at", "updated_at"])


def restore_project(project: Project) -> None:
    project.status = Project.Status.ACTIVE
    project.archived_at = None
    project.save(update_fields=["status", "archived_at", "updated_at"])


def _copy_name(name: str) -> str:
    suffix = " (copy)"
    return f"{name[: 200 - len(suffix)]}{suffix}"
