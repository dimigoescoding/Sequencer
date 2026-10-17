"""A foundation-installation project owned by one user."""

from django.conf import settings
from django.db import models
from django.urls import reverse


class Project(models.Model):
    class PackageType(models.TextChoices):
        FOUNDATION = "Foundation", "Foundation"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    package_type = models.CharField(
        max_length=32,
        choices=PackageType.choices,
        default=PackageType.FOUNDATION,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "name"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(package_type="Foundation"),
                name="project_package_is_foundation",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("projects:detail", args=[self.pk])

    @property
    def active_dataset(self):
        return self.dataset_versions.filter(is_active=True).first()
