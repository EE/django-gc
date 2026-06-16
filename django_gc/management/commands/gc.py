from argparse import ArgumentParser
from typing import Any, Callable

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.db.models import Model, QuerySet

from django_gc.core import find_fk_fields, get_combined_config


class Command(BaseCommand):
    """Remove unreferenced model instances from configured models."""
    help = 'Remove unreferenced model instances (garbage collection)'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--batch-size', type=int, default=1000, help='Batch size')
        parser.add_argument('--delete', action='store_true', help='Actually delete (default is dry run)')
        parser.add_argument('--model', type=str, help='Specific model to process (app_label.model_name)')

    def handle(self, *args: Any, **options: Any) -> None:
        batch_size = options['batch_size']
        delete = options['delete']
        specific_model = options.get('model')

        if not delete:
            print('DRY RUN MODE - use --delete to actually delete')

        total_deleted = 0

        combined_config = get_combined_config()

        for model_label, config in combined_config.items():
            if specific_model and model_label != specific_model:
                continue

            model = apps.get_model(model_label)

            print(f"\nProcessing {model_label}")
            deleted = garbage_collect_model(model, config, batch_size, delete)
            total_deleted += deleted

            if delete:
                print(f'Deleted {deleted} {model._meta.verbose_name_plural}')
            else:
                print(f'Would delete {deleted} {model._meta.verbose_name_plural}')

        print(f"\nTotal: {total_deleted}")


def garbage_collect_model(
    model: type[Model],
    config: dict[str, Any],
    batch_size: int = 1000,
    delete: bool = False,
) -> int:
    """Garbage collect a single model."""
    fk_fields = find_fk_fields(model, config.get('ignored_referencing_fields', []))

    print(f'Found {len(fk_fields)} FK fields referencing {model._meta.label}')
    for ref_model, field in fk_fields:
        print(f'  - {ref_model._meta.label}.{field.name}')

    filter_func: Callable[[QuerySet[Model]], QuerySet[Model]] | None = config.get('filter')
    if not filter_func:
        def filter_func(qs: QuerySet[Model]) -> QuerySet[Model]:
            return qs

    last_processed_id = None
    total_deleted = 0

    while True:
        batch_deleted, last_id, checked_count = process_batch(
            model, last_processed_id, batch_size, fk_fields, delete,
            filter_func=filter_func,
        )
        total_deleted += batch_deleted

        if checked_count < batch_size:  # No more instances to process
            break

        last_processed_id = last_id

    return total_deleted


@transaction.atomic
def process_batch(
    model: type[Model],
    last_processed_id: Any,
    batch_size: int,
    fk_fields: list[tuple[type[Model], models.ForeignKey[Model, Model]]],
    delete: bool = False,
    *,
    filter_func: Callable[[QuerySet[Model]], QuerySet[Model]],
) -> tuple[int, Any, int]:
    """Process a single batch of model instances."""
    # Get batch of instances
    # Model.objects is present at runtime but mypy doesn't recognize it on type[Model]
    queryset = model.objects.order_by('pk')  # type: ignore[attr-defined]
    queryset = filter_func(queryset)
    if last_processed_id is not None:
        queryset = queryset.filter(pk__gt=last_processed_id)

    instance_ids = set(queryset.values_list('pk', flat=True)[:batch_size])
    last_id = max(instance_ids) if instance_ids else None
    checked_count = len(instance_ids)

    # Find which instances are referenced by foreign keys
    referenced_ids = set()
    for ref_model, field in fk_fields:
        refs = ref_model.objects.filter(  # type: ignore[attr-defined]
            **{f'{field.name}__in': instance_ids}
        ).values_list(field.name, flat=True)
        referenced_ids.update(refs)

    # Find unreferenced instances
    deletable_ids = instance_ids - referenced_ids

    print(f'Batch ending at {last_id}: {len(deletable_ids)} deletable')

    if delete and deletable_ids:
        deleted_count, deleted_dict = model.objects.filter(pk__in=deletable_ids).delete()  # type: ignore[attr-defined]
        return deleted_dict.get(model._meta.label, 0), last_id, checked_count

    return len(deletable_ids), last_id, checked_count
