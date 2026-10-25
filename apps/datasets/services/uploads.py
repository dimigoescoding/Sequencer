"""Store an uploaded workbook as a new immutable dataset version."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from apps.datasets.models import (
    Cable,
    DatasetIssue,
    DatasetVersion,
    Foundation,
    ProgrammeSlot,
    WtgLocation,
)
from apps.datasets.services.parsing import UploadRejected, parse_workbook
from apps.projects.models import Project


def safe_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not cleaned.lower().endswith(".xlsx"):
        cleaned = f"{cleaned}.xlsx"
    return cleaned[:120] or "upload.xlsx"


def create_dataset_version(
    *, project: Project, user, filename: str, content: bytes
) -> DatasetVersion:
    parsed = parse_workbook(content)
    with transaction.atomic():
        version_number = (
            project.dataset_versions.order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
            or 0
        ) + 1
        version = DatasetVersion(
            project=project,
            version_number=version_number,
            original_filename=Path(filename).name[:255],
            content_sha256=hashlib.sha256(content).hexdigest(),
            row_count=len(parsed.foundations) + len(parsed.cables) + len(parsed.wtg_rows),
            included_count=(
                sum(1 for item in parsed.foundations if item.include)
                + sum(1 for item in parsed.cables if item.include)
                + sum(1 for item in parsed.wtg_rows if item.include)
            ),
            error_count=parsed.error_count,
            warning_count=parsed.warning_count,
            columns_json=parsed.columns,
            created_by=user,
        )
        version.original_file.save(safe_filename(filename), ContentFile(content), save=False)
        version.save()
        Foundation.objects.bulk_create(
            [
                Foundation(
                    dataset_version=version,
                    source_row=source_row,
                    foundation_id=item.foundation_id,
                    include=item.include,
                    weight_t=item.weight_t,
                    delivery_sequence=item.delivery_sequence,
                    length_m=item.length_m,
                    delivery_batch=item.delivery_batch,
                    easting_m=item.easting_m,
                    northing_m=item.northing_m,
                    punch_through=item.punch_through,
                    difficulty_value=item.difficulty_value,
                    eccentricity_limit_m=item.eccentricity_limit_m,
                    fixed_trip=item.fixed_trip,
                    fixed_position=item.fixed_position,
                    earliest_sequence=item.earliest_sequence,
                    latest_sequence=item.latest_sequence,
                    notes=item.notes,
                    attributes=item.attributes,
                )
                for item, source_row in zip(
                    parsed.foundations,
                    parsed.source_rows or [None] * len(parsed.foundations),
                    strict=False,
                )
            ]
        )
        DatasetIssue.objects.bulk_create(
            [
                DatasetIssue(
                    dataset_version=version,
                    severity=issue.severity,
                    code=issue.code,
                    message=issue.message,
                    row_number=issue.row_number,
                    column_name=issue.column_name,
                )
                for issue in parsed.issues
            ]
        )
        Cable.objects.bulk_create(
            [
                Cable(
                    dataset_version=version,
                    source_row=item.source_row,
                    cable_id=item.cable_id,
                    nickname=item.nickname,
                    include=item.include,
                    string_id=item.string_id,
                    loop_id=item.loop_id,
                    start_location_id=item.start_location_id,
                    end_location_id=item.end_location_id,
                    spider_cable=item.spider_cable,
                )
                for item in parsed.cables
            ]
        )
        WtgLocation.objects.bulk_create(
            [
                WtgLocation(
                    dataset_version=version,
                    source_row=item.source_row,
                    wtg_id=item.wtg_id,
                    include=item.include,
                    structure=item.structure,
                    easting_m=item.easting_m,
                    northing_m=item.northing_m,
                    spider_location=item.spider_location,
                    string_label=item.string_label,
                    jacking_difficulty=item.jacking_difficulty,
                )
                for item in parsed.wtg_rows
            ]
        )
        ProgrammeSlot.objects.bulk_create(
            [
                ProgrammeSlot(
                    dataset_version=version,
                    source_row=item.source_row,
                    slot=item.slot,
                    fou_p50_start=item.fou_p50_start,
                    fou_p50_end=item.fou_p50_end,
                    iac_p50_start=item.iac_p50_start,
                    iac_p50_end=item.iac_p50_end,
                    wtg_p50_start=item.wtg_p50_start,
                    wtg_p50_end=item.wtg_p50_end,
                )
                for item in parsed.programme
            ]
        )
    return version


def activate_dataset(version: DatasetVersion) -> None:
    if not version.can_activate:
        raise ValueError("A dataset with critical errors cannot be activated.")
    with transaction.atomic():
        version.project.dataset_versions.exclude(pk=version.pk).update(is_active=False)
        version.is_active = True
        version.save(update_fields=["is_active"])


__all__ = ["UploadRejected", "activate_dataset", "create_dataset_version", "safe_filename"]
