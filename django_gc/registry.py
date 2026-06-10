"""Registry for garbage collection configuration."""

from typing import Any

from django.apps import apps


def get_gc_registry() -> dict[str, dict[str, Any]]:
    """
    Discover and return garbage collection configuration from Django models.

    Models can define GC configuration using class attributes:
    - gc_enabled: Boolean to control whether model should be garbage collected (required)
    - gc_ignored_referencing_fields: List of field paths to ignore
    - gc_filter: Function to filter queryset for cleanup candidates

    Returns:
        dict: Model label -> configuration mapping
    """
    registry = {}

    for model in apps.get_models():
        # gc_enabled must be True for the model to be garbage collected
        if not (hasattr(model, 'gc_enabled') and model.gc_enabled):
            continue

        config = {}

        # Check for ignored referencing fields
        if hasattr(model, 'gc_ignored_referencing_fields'):
            config['ignored_referencing_fields'] = model.gc_ignored_referencing_fields

        # Check for filter function
        if hasattr(model, 'gc_filter'):
            config['filter'] = model.gc_filter

        # Always add to registry since we have gc_enabled=True
        registry[model._meta.label] = config

    return registry
