"""Celery application instance, auto-discovering tasks from installed apps."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("api")

# Read config from Django settings, the CELERY_ namespace.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks.py modules in every installed app.
app.autodiscover_tasks()
