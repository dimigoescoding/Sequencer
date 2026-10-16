"""User-defined sequencing constraints. Nothing here is inferred."""

from django.db import models

from apps.constraints.library import CONSTRAINT_TYPES


class Constraint(models.Model):
    class Enforcement(models.TextChoices):
        HARD = "hard", "Hard"
        SOFT = "soft", "Soft"

    scenario = models.ForeignKey(
        "scenarios.Scenario", on_delete=models.CASCADE, related_name="constraints"
    )
    name = models.CharField(max_length=200)
    constraint_type = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    enforcement = models.CharField(max_length=8, choices=Enforcement.choices)
    severity = models.PositiveSmallIntegerField(null=True, blank=True)
    scope = models.CharField(max_length=32, blank=True)
    parameters_json = models.JSONField(default=dict)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "id"]
        indexes = [
            models.Index(fields=["scenario", "active"]),
            models.Index(fields=["scenario", "display_order"]),
            models.Index(fields=["constraint_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(enforcement="soft") | models.Q(severity__isnull=True),
                name="hard_constraint_has_no_severity",
            ),
            models.CheckConstraint(
                condition=~models.Q(enforcement="soft")
                | models.Q(severity__gte=1, severity__lte=100),
                name="soft_constraint_severity_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def type_label(self) -> str:
        return CONSTRAINT_TYPES.get(self.constraint_type, {}).get("label", self.constraint_type)
