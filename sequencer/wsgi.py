"""WSGI entry point for Gunicorn."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sequencer.settings.local")

application = get_wsgi_application()
