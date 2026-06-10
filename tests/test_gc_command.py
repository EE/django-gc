import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tests.testapp.models import Document, Reference


@pytest.mark.django_db
def test_dry_run_does_not_delete() -> None:
    unreferenced = Document.objects.create()

    call_command('gc')

    assert Document.objects.filter(pk=unreferenced.pk).exists()


@pytest.mark.django_db
def test_delete_removes_unreferenced_and_keeps_referenced() -> None:
    unreferenced = Document.objects.create()
    referenced = Document.objects.create()
    Reference.objects.create(document=referenced)

    call_command('gc', '--delete')

    assert not Document.objects.filter(pk=unreferenced.pk).exists()
    assert Document.objects.filter(pk=referenced.pk).exists()


@pytest.mark.django_db
def test_settings_config(settings) -> None:
    settings.GARBAGE_COLLECTION_CONFIG = {
        'testapp.Reference': {},
    }
    referenced = Document.objects.create()
    Reference.objects.create(document=referenced)

    call_command('gc', '--delete', '--model', 'testapp.Reference')

    # Nothing references Reference, so it is deleted; Document is untouched
    # because the command was limited to a single model.
    assert not Reference.objects.exists()
    assert Document.objects.filter(pk=referenced.pk).exists()


@pytest.mark.django_db
def test_collision_between_settings_and_model_config(settings) -> None:
    settings.GARBAGE_COLLECTION_CONFIG = {
        'testapp.Document': {},
    }

    with pytest.raises(CommandError, match='collision'):
        call_command('gc')
