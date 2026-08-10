"""Copy this file to settings.py and configure its environment variables."""

import os

from .settings_defaults import *  # noqa: F401,F403


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Set the DJANGO_SECRET_KEY environment variable.")

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "itam_db"),
        "USER": os.environ.get("DB_USER", "itam_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}
