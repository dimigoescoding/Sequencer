"""Production settings for Render."""

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import CSRF_TRUSTED_ORIGINS

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith("dev-only"):
    raise ImproperlyConfigured("Set a unique SECRET_KEY in the environment.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", ".onrender.com").split(",")
    if host.strip()
]

render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
if render_url:
    host = urlparse(render_url).hostname
    if (
        host
        and host not in ALLOWED_HOSTS
        and not any(allowed.startswith(".") and host.endswith(allowed) for allowed in ALLOWED_HOSTS)
    ):
        ALLOWED_HOSTS.append(host)
    if render_url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_url)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() in {"1", "true", "yes"}
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False  # noqa: F405

STORAGES = {
    "default": {
        "BACKEND": "apps.datasets.storage.DatabaseStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
