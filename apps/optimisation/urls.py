from django.urls import path

from apps.optimisation import views

app_name = "optimisation"

urlpatterns = [
    path("<int:run_id>/", views.run_detail, name="detail"),
    path("<int:run_id>/export/", views.run_export, name="export"),
]
