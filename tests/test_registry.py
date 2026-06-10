from typing import Optional
from unittest.mock import patch

import pytest

from django_gc.registry import get_gc_registry


@pytest.mark.parametrize("gc_enabled", [True, False, None])
def test_registry_gc_enabled_behavior(gc_enabled: Optional[bool]) -> None:
    """Test that registry only picks up models with gc_enabled=True and ignores others."""

    class MockModel:
        class _meta:
            label = 'test_app.MockModel'

    # Set gc_enabled attribute based on parameter
    if gc_enabled is not None:
        setattr(MockModel, 'gc_enabled', gc_enabled)

    # Add some GC configuration to make it more realistic
    setattr(MockModel, 'gc_ignored_referencing_fields', ['app.Model.field'])

    with patch('django_gc.registry.apps.get_models') as mock_get_models:
        mock_get_models.return_value = [MockModel]

        registry = get_gc_registry()

        if gc_enabled is True:
            # Should be included in registry
            assert 'test_app.MockModel' in registry
            config = registry['test_app.MockModel']
            assert config['ignored_referencing_fields'] == ['app.Model.field']
        else:
            # Should NOT be included in registry (gc_enabled=False or None)
            assert 'test_app.MockModel' not in registry
