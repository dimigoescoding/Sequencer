"""User-defined sequencing constraints. Nothing here is inferred."""

from django.db import models

from apps.constraints.library import CONSTRAINT_TYPES


class Constraint(models.Model):
    class Enforcement(models.TextChoices):
        HARD = "hard", "Hard"
        SOFT = "soft", "Soft"

    class Package(models.TextChoices):
        FOU = "FOU", "FOU"
        IAC = "IAC", "IAC"
        WTG = "WTG", "WTG"

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
    package = models.CharField(max_length=8, choices=Package.choices, default=Package.FOU)
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

    @property
    def parameter_summary(self) -> str:
        parameters = self.parameters_json or {}
        if self.constraint_type == "loop_id_sequence":
            return "Loop ID in IAC sheet order"
        if self.constraint_type == "string_id_sequence":
            return "String ID letter and number on the WTG sheet"
        if self.constraint_type == "package_buffer":
            if parameters.get("mode") == "maximize":
                return "maximize"
            if parameters.get("minimum_days") not in (None, ""):
                return f"minimum {parameters['minimum_days']} days"
            return ""
        if self.constraint_type != "earliest_sequence":
            return ""
        if parameters.get("attribute"):
            parts = [str(parameters.get("attribute") or ""), str(parameters.get("operator") or "")]
            value = parameters.get("value")
            if value not in (None, ""):
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                parts.append(str(value))
            subject = " ".join(part for part in parts if part)
        else:
            subject = str(parameters.get("foundation_id") or "")
        if parameters.get("earliest_trip") not in (None, ""):
            bound = f"earliest trip {parameters['earliest_trip']}"
        elif parameters.get("earliest_sequence") not in (None, ""):
            bound = f"earliest sequence {parameters['earliest_sequence']}"
        else:
            bound = ""
        return ", ".join(part for part in (subject, bound) if part)
