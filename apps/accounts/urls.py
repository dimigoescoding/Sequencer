from django.contrib.auth.views import LogoutView, PasswordChangeDoneView
from django.urls import path

from apps.accounts.views import AccountView, SequencerLoginView, SequencerPasswordChangeView

app_name = "accounts"

urlpatterns = [
    path("login/", SequencerLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/", SequencerPasswordChangeView.as_view(), name="password_change"),
    path(
        "password/done/",
        PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
    path("", AccountView.as_view(), name="account"),
]
