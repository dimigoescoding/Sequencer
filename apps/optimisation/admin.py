from django.contrib import admin

from apps.optimisation.models import OptimisationRun


@admin.register(OptimisationRun)
class OptimisationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "scenario", "status", "solver_status", "validation_status", "created_at")
    list_filter = ("status", "validation_status")
