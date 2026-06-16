"""Shared helpers used by more than one garbage collection command."""

from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError
from django.db import models
from django.db.models import Model

from django_gc.registry import get_gc_registry


def get_combined_config() -> dict[str, dict[str, Any]]:
    """Return the garbage collection config for all configured models.

    Combines ``settings.GARBAGE_COLLECTION_CONFIG`` with the registry-discovered
    config from model class attributes, raising if a model is configured in both
    places.
    """
    hardcoded_config = getattr(settings, 'GARBAGE_COLLECTION_CONFIG', {})
    registry_config = get_gc_registry()

    collisions = set(hardcoded_config.keys()) & set(registry_config.keys())
    if collisions:
        raise CommandError(
            f"Configuration collision detected for models: {', '.join(sorted(collisions))}. "
            "Models cannot be configured both in settings.GARBAGE_COLLECTION_CONFIG "
            "and via model class attributes."
        )

    combined_config = hardcoded_config.copy()
    combined_config.update(registry_config)
    return combined_config


def find_fk_fields(
    target_model: type[Model],
    ignored_fields: list[str],
) -> list[tuple[type[Model], models.ForeignKey[Model, Model]]]:
    """Find all ForeignKey fields pointing to target_model, excluding ignored fields."""
    fk_fields = []
    ignored_set = set(ignored_fields)
    matched_ignored = set()

    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, models.ForeignKey) and field.related_model == target_model:
                field_path = f"{model._meta.label}.{field.name}"
                if field_path in ignored_set:
                    matched_ignored.add(field_path)
                else:
                    fk_fields.append((model, field))

    unmatched_ignored = ignored_set - matched_ignored
    if unmatched_ignored:
        raise CommandError(
            f"Ignored referencing fields for {target_model._meta.label} do not match "
            f"any ForeignKey pointing to it: {', '.join(sorted(unmatched_ignored))}. "
            "The configuration is stale or contains a typo."
        )

    return fk_fields
