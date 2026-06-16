import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from django_gc.management.commands.gc_inspect import inspect_object
from tests.testapp.models import Cache, CacheLog, Document, Reference


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
def test_ignored_referencing_field_does_not_keep_row_alive() -> None:
    cache = Cache.objects.create()
    CacheLog.objects.create(cache=cache)

    call_command('gc', '--delete', '--model', 'testapp.Cache')

    assert not Cache.objects.exists()
    # The ignored reference goes away with the cascade.
    assert not CacheLog.objects.exists()


@pytest.mark.django_db
def test_unmatched_ignored_field_path_fails_loudly(settings) -> None:
    settings.GARBAGE_COLLECTION_CONFIG = {
        'testapp.Reference': {
            'ignored_referencing_fields': ['testapp.Document.no_such_field'],
        },
    }

    # Even a dry run reports the stale path.
    with pytest.raises(CommandError, match='no_such_field'):
        call_command('gc', '--model', 'testapp.Reference')


@pytest.mark.django_db
def test_collision_between_settings_and_model_config(settings) -> None:
    settings.GARBAGE_COLLECTION_CONFIG = {
        'testapp.Document': {},
    }

    with pytest.raises(CommandError, match='collision'):
        call_command('gc')


@pytest.mark.django_db
def test_inspect_object_not_found() -> None:
    result = inspect_object(Document, {}, 999999)

    assert result.status == 'not_found'
    assert result.references == []


@pytest.mark.django_db
def test_inspect_object_collectable() -> None:
    document = Document.objects.create()

    result = inspect_object(Document, {}, document.pk)

    assert result.status == 'collectable'
    assert result.references == []


@pytest.mark.django_db
def test_inspect_object_referenced_lists_referencing_objects() -> None:
    document = Document.objects.create()
    reference = Reference.objects.create(document=document)

    result = inspect_object(Document, {}, document.pk)

    assert result.status == 'referenced'
    assert result.references == [f'testapp.Reference.document (pk={reference.pk})']
    assert 'referenced by 1 other object' in result.message


@pytest.mark.django_db
def test_inspect_object_excluded_by_filter() -> None:
    document = Document.objects.create()
    config = {'filter': lambda qs: qs.none()}

    result = inspect_object(Document, config, document.pk)

    assert result.status == 'excluded_by_filter'


@pytest.mark.django_db
def test_inspect_ignores_ignored_referencing_fields() -> None:
    cache = Cache.objects.create()
    CacheLog.objects.create(cache=cache)
    config = {'ignored_referencing_fields': ['testapp.CacheLog.cache']}

    result = inspect_object(Cache, config, cache.pk)

    # The ignored reference does not keep the row alive.
    assert result.status == 'collectable'


@pytest.mark.django_db
def test_inspect_command_unconfigured_model_fails() -> None:
    with pytest.raises(CommandError, match='not configured'):
        call_command('gc_inspect', 'testapp.Reference', '1')


@pytest.mark.django_db
def test_inspect_command_does_not_delete() -> None:
    document = Document.objects.create()

    call_command('gc_inspect', 'testapp.Document', str(document.pk))

    assert Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
def test_inspect_command_renders_references(capsys) -> None:
    document = Document.objects.create()
    reference = Reference.objects.create(document=document)

    call_command('gc_inspect', 'testapp.Document', str(document.pk))

    out = capsys.readouterr().out
    assert 'object referenced by 1 other object' in out
    assert f'- testapp.Reference.document (pk={reference.pk})' in out
