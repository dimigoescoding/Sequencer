from django.urls import path

from apps.constraints import views

app_name = "constraints"

urlpatterns = [
    path("", views.constraint_list, name="list"),
    path("<int:constraint_id>/toggle/", views.constraint_toggle, name="toggle"),
]
