from django.urls import path

from apps.constraints import views

app_name = "constraints"

urlpatterns = [
    path("", views.constraint_list, name="list"),
    path("new/", views.constraint_choose, name="choose"),
    path("new/<slug:constraint_type>/", views.constraint_create, name="create"),
    path("<int:constraint_id>/edit/", views.constraint_edit, name="edit"),
    path("<int:constraint_id>/duplicate/", views.constraint_duplicate, name="duplicate"),
    path("<int:constraint_id>/toggle/", views.constraint_toggle, name="toggle"),
    path("<int:constraint_id>/delete/", views.constraint_delete, name="delete"),
    path("<int:constraint_id>/move/", views.constraint_move, name="move"),
]
