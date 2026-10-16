from django.urls import path

from apps.projects import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("archived/", views.archived_list, name="archived"),
    path("new/", views.project_create, name="create"),
    path("<int:project_id>/", views.project_detail, name="detail"),
    path("<int:project_id>/edit/", views.project_edit, name="edit"),
    path("<int:project_id>/duplicate/", views.project_duplicate, name="duplicate"),
    path("<int:project_id>/archive/", views.project_archive, name="archive"),
    path("<int:project_id>/restore/", views.project_restore, name="restore"),
    path("<int:project_id>/vessel/", views.project_vessel, name="vessel"),
    path("<int:project_id>/runs/", views.project_runs, name="runs"),
]
