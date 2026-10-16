from django.contrib import admin

from apps.projects.models import Project

admin.site.site_header = "Sequencer administration"


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "package_type", "status", "updated_at")
    list_filter = ("status", "package_type")
    search_fields = ("name", "owner__username")
