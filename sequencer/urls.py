"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("projects/<int:project_id>/data/", include("apps.datasets.urls")),
    path("projects/<int:project_id>/scenarios/", include("apps.scenarios.urls")),
    path(
        "projects/<int:project_id>/scenarios/<int:scenario_id>/constraints/",
        include("apps.constraints.urls"),
    ),
    path("runs/", include("apps.optimisation.urls")),
    path("", RedirectView.as_view(pattern_name="projects:list", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
