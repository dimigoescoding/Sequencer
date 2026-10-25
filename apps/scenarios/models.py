"""Scenarios hold vessel settings, constraints, and optimisation runs."""

from django.db import models
from django.urls import reverse


class Scenario(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="scenarios"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    dataset_version = models.ForeignKey(
        "datasets.DatasetVersion",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scenarios",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["dataset_version"]),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("scenarios:detail", args=[self.project_id, self.pk])


class VesselSettings(models.Model):
    scenario = models.OneToOneField(
        Scenario, on_delete=models.CASCADE, related_name="vessel_settings"
    )
    max_foundations_per_trip = models.PositiveIntegerField(default=4)
    wtg_per_trip = models.PositiveIntegerField(default=4)
    allow_partial_final_trip = models.BooleanField(default=True)
    base_maximum_trip_payload_t = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    solver_time_limit_seconds = models.PositiveIntegerField(default=20)
    transit_speed_knots = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    harbour_easting_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    harbour_northing_m = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    workbook_values = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["scenario"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_foundations_per_trip__gte=1),
                name="vessel_capacity_at_least_one",
            ),
            models.CheckConstraint(
                condition=models.Q(wtg_per_trip__gte=1),
                name="wtg_per_trip_at_least_one",
            ),
            models.CheckConstraint(
                condition=models.Q(solver_time_limit_seconds__gte=1),
                name="solver_time_limit_at_least_one",
            ),
            models.CheckConstraint(
                condition=models.Q(solver_time_limit_seconds__lte=600),
                name="solver_time_limit_at_most_600",
            ),
        ]

    def __str__(self) -> str:
        return f"Vessel settings for {self.scenario}"
