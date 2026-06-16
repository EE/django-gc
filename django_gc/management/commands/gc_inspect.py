from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import Any, Callable

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Model, QuerySet

from django_gc.core import find_fk_fields, get_combined_config


class Command(BaseCommand):
    """Report the garbage collection status of a single object.

    Read-only: explains why a specific row is or is not garbage collected
    without deleting anything.
    """

    help = 'Report the garbage collection status of a single object'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('model', type=str, help='Model to inspect (app_label.model_name)')
        parser.add_argument('pk', type=str, help='Primary key of the object to inspect')

    def handle(self, *args: Any, **options: Any) -> None:
        model_label = options['model']
        pk = options['pk']

        combined_config = get_combined_config()
        if model_label not in combined_config:
            raise CommandError(
                f'{model_label} is not configured for garbage collection.'
            )

        model = apps.get_model(model_label)
        result = inspect_object(model, combined_config[model_label], pk)

        print(result.message)
        for reference in result.references:
            print(f'  - {reference}')


@dataclass
class InspectResult:
    """The garbage collection status of a single object.

    ``status`` is one of ``'not_found'``, ``'excluded_by_filter'``,
    ``'referenced'`` (with the blocking foreign keys in ``references``), or
    ``'collectable'``.
    """

    status: str
    message: str
    references: list[str] = field(default_factory=list)


def inspect_object(
    model: type[Model],
    config: dict[str, Any],
    pk: Any,
) -> InspectResult:
    """Report the garbage collection status of a single object.

    Mirrors the decisions made by the gc command (filter, then foreign key
    references) without deleting anything, so it can be used to explain why a
    specific row is or is not collected.
    """
    label = model._meta.label
    fk_fields = find_fk_fields(model, config.get('ignored_referencing_fields', []))

    # Model.objects is present at runtime but mypy doesn't recognize it on type[Model]
    if not model.objects.filter(pk=pk).exists():  # type: ignore[attr-defined]
        return InspectResult('not_found', f'{label} pk={pk}: object not found')

    filter_func: Callable[[QuerySet[Model]], QuerySet[Model]] | None = config.get('filter')
    if filter_func is not None:
        candidates = filter_func(model.objects.all())  # type: ignore[attr-defined]
        if not candidates.filter(pk=pk).exists():
            return InspectResult(
                'excluded_by_filter',
                f'{label} pk={pk}: object excluded by filter (not currently a collection candidate)',
            )

    references = []
    for ref_model, fk_field in fk_fields:
        ref_pks = ref_model.objects.filter(  # type: ignore[attr-defined]
            **{fk_field.name: pk}
        ).values_list('pk', flat=True)
        for ref_pk in ref_pks:
            references.append(f'{ref_model._meta.label}.{fk_field.name} (pk={ref_pk})')

    if references:
        plural = 's' if len(references) != 1 else ''
        return InspectResult(
            'referenced',
            f'{label} pk={pk}: object referenced by {len(references)} other object{plural}',
            references,
        )

    return InspectResult(
        'collectable',
        f'{label} pk={pk}: object is unreferenced and would be collected',
    )
