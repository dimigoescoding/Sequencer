from django.contrib import admin

from apps.constraints.models import Constraint


@admin.register(Constraint)
class ConstraintAdmin(admin.ModelAdmin):
    list_display = ("name", "scenario", "constraint_type", "enforcement", "severity", "active")
    list_filter = ("enforcement", "active", "constraint_type")
