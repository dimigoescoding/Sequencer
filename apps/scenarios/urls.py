from django.urls import path

from apps.scenarios import views

app_name = "scenarios"

urlpatterns = [
    path("", views.scenario_list, name="list"),
    path("new/", views.scenario_create, name="create"),
    path("<int:scenario_id>/", views.scenario_detail, name="detail"),
    path("<int:scenario_id>/edit/", views.scenario_edit, name="edit"),
    path("<int:scenario_id>/duplicate/", views.scenario_duplicate, name="duplicate"),
    path("<int:scenario_id>/delete/", views.scenario_delete, name="delete"),
    path("<int:scenario_id>/settings/", views.vessel_settings, name="settings"),
    path("<int:scenario_id>/generate/", views.generate, name="generate"),
    path("<int:scenario_id>/runs/", views.scenario_runs, name="runs"),
]
