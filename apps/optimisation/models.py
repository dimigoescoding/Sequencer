"""Persisted solver runs and the independent validation record."""

from django.db import models


class OptimisationRun(models.Model):
    class Status(models.TextChoices):
        OPTIMAL = "OPTIMAL", "OPTIMAL"
        FEASIBLE = "FEASIBLE", "FEASIBLE"
        INFEASIBLE = "INFEASIBLE", "INFEASIBLE"
        UNKNOWN = "UNKNOWN", "UNKNOWN"
        ERROR = "ERROR", "ERROR"
        INVALID = "INVALID", "INVALID"

    class ValidationStatus(models.TextChoices):
        PASSED = "Passed", "Passed"
        FAILED = "Failed", "Failed"
        NOT_RUN = "Not run", "Not run"

    scenario = models.ForeignKey(
        "scenarios.Scenario", on_delete=models.CASCADE, related_name="runs"
    )
    dataset_version = models.ForeignKey(
        "datasets.DatasetVersion",
        on_delete=models.CASCADE,
        related_name="runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    solver_status = models.CharField(max_length=16, choices=Status.choices)
    validation_status = models.CharField(
        max_length=16,
        choices=ValidationStatus.choices,
        default=ValidationStatus.NOT_RUN,
    )
    objective_value = models.BigIntegerField(null=True, blank=True)
    runtime_seconds = models.FloatField(default=0)
    seed = models.PositiveIntegerField(default=1)
    message = models.TextField(blank=True)
    included_count = models.PositiveIntegerField(default=0)
    trip_count = models.PositiveIntegerField(default=0)
    hard_constraint_count = models.PositiveIntegerField(default=0)
    soft_constraint_count = models.PositiveIntegerField(default=0)
    soft_tradeoff_count = models.PositiveIntegerField(default=0)
    vessel_snapshot = models.JSONField(default=dict)
    constraint_snapshot = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scenario", "status"]),
            models.Index(fields=["scenario", "created_at"]),
            models.Index(fields=["dataset_version"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Run {self.pk} ({self.status})"

    @property
    def approved(self) -> bool:
        return (
            self.status in {self.Status.OPTIMAL, self.Status.FEASIBLE}
            and self.validation_status == "Passed"
        )


class SequenceResult(models.Model):
    run = models.ForeignKey(OptimisationRun, on_delete=models.CASCADE, related_name="sequence_rows")
    installation_sequence = models.PositiveIntegerField()
    trip = models.PositiveIntegerField()
    vessel_position = models.PositiveIntegerField()
    foundation_id = models.CharField(max_length=100)
    weight_t = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    trip_total_weight_t = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    delivery_sequence = models.PositiveIntegerField(null=True, blank=True)
    sequence_deviation = models.IntegerField(null=True, blank=True)
    delivery_batch = models.CharField(max_length=100, blank=True)
    difficulty_value = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    punch_through = models.BooleanField(null=True)
    fixed_trip = models.PositiveIntegerField(null=True, blank=True)
    fixed_position = models.PositiveIntegerField(null=True, blank=True)
    earliest_sequence = models.PositiveIntegerField(null=True, blank=True)
    latest_sequence = models.PositiveIntegerField(null=True, blank=True)
    hard_constraint_status = models.CharField(max_length=16, blank=True)
    soft_penalty = models.IntegerField(default=0)
    governing_constraints = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["installation_sequence"]
        indexes = [
            models.Index(fields=["run", "installation_sequence"]),
            models.Index(fields=["run", "foundation_id"]),
            models.Index(fields=["run", "trip"]),
        ]


class TripResult(models.Model):
    run = models.ForeignKey(OptimisationRun, on_delete=models.CASCADE, related_name="trip_rows")
    trip = models.PositiveIntegerField()
    foundation_count = models.PositiveIntegerField()
    foundations_in_order = models.TextField(blank=True)
    payload_limit_t = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    total_weight_t = models.DecimalField(max_digits=14, decimal_places=3)
    remaining_payload_t = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    punch_through_count = models.PositiveIntegerField(default=0)
    average_difficulty = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    maximum_difficulty = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    route_distance = models.DecimalField(max_digits=16, decimal_places=1, null=True, blank=True)
    payload_check = models.CharField(max_length=32, blank=True)
    position_check = models.CharField(max_length=32, blank=True)
    overall_trip_check = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["trip"]
        indexes = [models.Index(fields=["run", "trip"])]


class ValidationResult(models.Model):
    run = models.ForeignKey(
        OptimisationRun, on_delete=models.CASCADE, related_name="validation_rows"
    )
    check_name = models.CharField(max_length=120)
    constraint_name = models.CharField(max_length=200, blank=True)
    target = models.TextField(blank=True)
    actual_result = models.TextField(blank=True)
    status = models.CharField(max_length=32)
    affected_foundations = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        indexes = [
            models.Index(fields=["run", "status"]),
            models.Index(fields=["run", "display_order"]),
        ]
