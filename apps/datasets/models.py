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
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["source_row", "id"]
        indexes = [
            models.Index(fields=["dataset_version", "foundation_id"]),
            models.Index(fields=["dataset_version", "include"]),
        ]

    def __str__(self) -> str:
        return self.foundation_id


class Cable(models.Model):
    """One inter-array cable. It joins two location ids and is not a point."""

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="cables"
    )
    source_row = models.PositiveIntegerField(null=True, blank=True)
    cable_id = models.CharField(max_length=100)
    nickname = models.CharField(max_length=200, blank=True)
    include = models.BooleanField(null=True)
    string_id = models.CharField(max_length=100, blank=True)
    loop_id = models.CharField(max_length=100, blank=True)
    start_location_id = models.CharField(max_length=100, blank=True)
    end_location_id = models.CharField(max_length=100, blank=True)
    spider_cable = models.BooleanField(null=True)

    class Meta:
        ordering = ["source_row", "id"]
        indexes = [
            models.Index(fields=["dataset_version", "cable_id"]),
            models.Index(fields=["dataset_version", "include"]),
        ]

    def __str__(self) -> str:
        return self.cable_id


class WtgLocation(models.Model):
    """One WTG installation activity. It is sequenced with FOU and IAC, not instead of them."""

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="wtg_locations"
    )
    source_row = models.PositiveIntegerField(null=True, blank=True)
    wtg_id = models.CharField(max_length=100)
    include = models.BooleanField(null=True)
    structure = models.CharField(max_length=100, blank=True)
    easting_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    northing_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    spider_location = models.BooleanField(null=True)
    string_label = models.CharField(max_length=100, blank=True)
    jacking_difficulty = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["source_row", "id"]
        indexes = [
            models.Index(fields=["dataset_version", "wtg_id"]),
            models.Index(fields=["dataset_version", "include"]),
        ]

    def __str__(self) -> str:
        return self.wtg_id


class ProgrammeSlot(models.Model):
    """One programme slot. Dates are per package and are not location ids."""

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="programme_slots"
    )
    source_row = models.PositiveIntegerField(null=True, blank=True)
    slot = models.PositiveIntegerField()
    fou_p50_start = models.DateTimeField(null=True, blank=True)
    fou_p50_end = models.DateTimeField(null=True, blank=True)
    iac_p50_start = models.DateTimeField(null=True, blank=True)
    iac_p50_end = models.DateTimeField(null=True, blank=True)
    wtg_p50_start = models.DateTimeField(null=True, blank=True)
    wtg_p50_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["slot", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset_version", "slot"], name="unique_programme_slot"
            )
        ]
        indexes = [models.Index(fields=["dataset_version", "slot"])]

    def __str__(self) -> str:
        return str(self.slot)


class StoredFile(models.Model):
    """Workbook bytes kept in the database so a Free Render instance can sleep."""

    path = models.CharField(max_length=300, unique=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["path"])]

    def __str__(self) -> str:
        return self.path


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


class DatasetConstraint(models.Model):
    """Constraint row copied from the workbook. The scenario can only switch it on or off."""

    class Enforcement(models.TextChoices):
        HARD = "hard", "Hard"
        SOFT = "soft", "Soft"

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="constraint_rows"
    )
    package = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=200)
    explanation = models.TextField(blank=True)
    enforcement = models.CharField(max_length=8, choices=Enforcement.choices)
    severity = models.PositiveSmallIntegerField(null=True, blank=True)
    reported_severity = models.CharField(max_length=32, blank=True)
    active = models.BooleanField(default=True)
    constraint_type = models.CharField(max_length=64)
    parameters_json = models.JSONField(default=dict)
    source_row = models.PositiveIntegerField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self) -> str:
        return self.name


class DatasetSetting(models.Model):
    """One setting from the workbook. The user may change the value, not the list."""

    dataset_version = models.ForeignKey(
        DatasetVersion, on_delete=models.CASCADE, related_name="setting_rows"
    )
    name = models.CharField(max_length=200)
    key = models.CharField(max_length=64)
    value = models.CharField(max_length=64)
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["source_row", "id"]

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"
