from django.contrib import admin

from apps.scenarios.models import Scenario, VesselSettings


class VesselSettingsInline(admin.StackedInline):
    model = VesselSettings


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status", "updated_at")
    inlines = [VesselSettingsInline]
