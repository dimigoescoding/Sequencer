from django.contrib import admin

from apps.datasets.models import DatasetIssue, DatasetVersion, Foundation


class FoundationInline(admin.TabularInline):
    model = Foundation
    extra = 0


@admin.register(DatasetVersion)
class DatasetVersionAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "version_number",
        "is_active",
        "error_count",
        "warning_count",
        "created_at",
    )
    inlines = [FoundationInline]


@admin.register(DatasetIssue)
class DatasetIssueAdmin(admin.ModelAdmin):
    list_display = ("dataset_version", "severity", "code", "row_number")
