from django.urls import path

from apps.datasets import views

app_name = "datasets"

urlpatterns = [
    path("", views.dataset_index, name="index"),
    path("upload/", views.dataset_upload, name="upload"),
    path("template/", views.dataset_template, name="template"),
    path("<int:version_id>/", views.dataset_version, name="version"),
    path("<int:version_id>/activate/", views.dataset_activate, name="activate"),
    path("<int:version_id>/original/", views.dataset_original, name="original"),
]
