from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.views.generic import TemplateView

from apps.ui import apply_bootstrap


class SequencerLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        apply_bootstrap(form)
        return form


class SequencerPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        apply_bootstrap(form)
        return form


class AccountView(LoginRequiredMixin, TemplateView):
    template_name = "account/account.html"
