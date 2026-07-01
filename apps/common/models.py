"""Reusable abstract base models for the rest of the project."""

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Adds self-updating ``created_at`` / ``updated_at`` fields."""

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Uses a non-sequential UUID primary key instead of an auto integer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """Convenience base combining a UUID pk with timestamps."""

    class Meta:
        abstract = True
