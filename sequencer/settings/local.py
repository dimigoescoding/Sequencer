"""Local development settings. SQLite by default. DEBUG is on."""

import os

from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = True
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-only-insecure-sequencer-key-not-for-production-use-0123456789",
)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver", "[::1]"]

if not os.environ.get("DATABASE_URL"):
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
