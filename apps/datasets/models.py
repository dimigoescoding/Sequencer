"""Immutable foundation dataset versions parsed from Excel."""

from django.conf import settings
from django.db import models


def dataset_upload_path(instance: "DatasetVersion", filename: str) -> str:
    return (
        f"datasets/user_{instance.project.owner_id}/project_{instance.project_id}/"
        f"v{instance.version_number}_{filename}"
    )


class DatasetVersion(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="dataset_versions"
    )
    version_number = models.PositiveIntegerField()
    original_file = models.FileField(upload_to=dataset_upload_path, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=False)
    row_count = models.PositiveIntegerField(default=0)
    included_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    columns_json = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dataset_versions",
    )

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version_number"], name="unique_dataset_version_number"
            )
        ]
        indexes = [
            models.Index(fields=["project", "is_active"]),
            models.Index(fields=["project", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project.name} v{self.version_number}"

    @property
    def can_activate(self) -> bool:
        return self.error_count == 0 and self.row_count > 0


class Foundation(models.Model):
    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="foundations"
    )
    source_row = models.PositiveIntegerField(null=True, blank=True)
    foundation_id = models.CharField(max_length=100)
    include = models.BooleanField(null=True)
    weight_t = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    delivery_sequence = models.PositiveIntegerField(null=True, blank=True)
    length_m = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    delivery_batch = models.CharField(max_length=100, blank=True)
    easting_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    northing_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    punch_through = models.BooleanField(null=True)
    difficulty_value = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    eccentricity_limit_m = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    fixed_trip = models.PositiveIntegerField(null=True, blank=True)
    fixed_position = models.PositiveIntegerField(null=True, blank=True)
    earliest_sequence = models.PositiveIntegerField(null=True, blank=True)
    latest_sequence = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["source_row", "id"]
        indexes = [
            models.Index(fields=["dataset_version", "foundation_id"]),
            models.Index(fields=["dataset_version", "include"]),
        ]

    def __str__(self) -> str:
        return self.foundation_id


class DatasetIssue(models.Model):
    class Severity(models.TextChoices):
        ERROR = "error", "Error"
        WARNING = "warning", "Warning"

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="issues"
    )
    severity = models.CharField(max_length=16, choices=Severity.choices)
    code = models.CharField(max_length=64)
    message = models.TextField()
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column_name = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["severity", "row_number", "id"]
        indexes = [models.Index(fields=["dataset_version", "severity"])]

    def __str__(self) -> str:
        return self.message
