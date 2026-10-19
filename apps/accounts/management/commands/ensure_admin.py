"""Create the first administrator when the environment supplies credentials.

Render Free web services have no shell, so this runs from the start command.
It creates the user once and does not reset a password that was changed later.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_* if that username does not exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not username or not email or not password:
            self.stdout.write("DJANGO_SUPERUSER_* is incomplete. No administrator was created.")
            return
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(f"User '{username}' already exists. The password was left unchanged.")
            return
        user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created administrator '{username}'."))
