# django-gc

Garbage collection for Django models: a management command that deletes model
instances which are no longer referenced by any foreign key.

This is useful for models that only matter while something points at them —
attachments, intermediate artifacts, denormalized blobs — where deleting the
referencing row should eventually make the referenced row go away too, without
scattering cleanup logic across the codebase.

## How it works

The `gc` management command:

1. Collects the set of models configured for garbage collection (see below).
2. For each configured model, finds every `ForeignKey` in the project that
   points to it.
3. Walks the model's rows in primary-key order, in batches, and deletes (or in
   dry-run mode, reports) every row whose primary key is not referenced by any
   of those foreign keys.

Each batch runs in its own transaction, so the command is safe to run against
large tables and can be interrupted without leaving partial work uncommitted.

## Installation

Install the package, then add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'django_gc.apps.DjangoGcConfig',
]
```

## Configuration

Models can be opted into garbage collection in two ways. A model must be
configured in exactly one of them — configuring the same model in both places
raises an error.

### Model class attributes

For models you own, declare the configuration on the model itself:

```python
class Attachment(models.Model):
    gc_enabled = True

    # Optional: foreign keys to this model that should NOT keep a row alive,
    # as "app_label.ModelName.field_name" paths.
    gc_ignored_referencing_fields = [
        'audit.AuditLog.attachment',
    ]

    # Optional: narrow which rows are considered for deletion at all,
    # e.g. to give recent rows a grace period.
    @staticmethod
    def gc_filter(queryset):
        return queryset.filter(
            created_at__lt=timezone.now() - datetime.timedelta(days=7),
        )
```

- `gc_enabled` (required, must be `True`) opts the model in.
- `gc_ignored_referencing_fields` (optional) lists referencing foreign keys to
  ignore when deciding whether a row is still in use. Every listed path must
  match an existing `ForeignKey` to the model — the command fails loudly on
  paths that don't (including in dry-run mode), so stale configuration is
  caught instead of silently changing behavior.
- `gc_filter` (optional) is a callable that receives the base queryset and
  returns the queryset of garbage collection candidates.

### Settings

For models you don't control (e.g. from third-party apps), configure them in
`settings.GARBAGE_COLLECTION_CONFIG`:

```python
GARBAGE_COLLECTION_CONFIG = {
    'thirdparty.SomeModel': {
        'ignored_referencing_fields': [
            'thirdparty.SomeLog.some_model',
        ],
        'filter': lambda qs: qs.filter(
            created_at__lt=timezone.now() - datetime.timedelta(days=7),
        ),
    },
}
```

The keys are model labels (`app_label.ModelName`); the per-model options are
the same as the model attribute equivalents above.

## Usage

The command is a dry run by default:

```
python manage.py gc
```

To actually delete:

```
python manage.py gc --delete
```

Options:

- `--delete` — actually delete rows (the default is a dry run that only
  reports what would be deleted).
- `--model app_label.ModelName` — only process a single configured model.
- `--batch-size N` — rows examined per transaction (default 1000).

## Inspecting a single object

The `gc_inspect` command reports the garbage collection status of one object
without deleting anything. It's useful for answering "why is this row still
here?" or "would this row be collected on the next run?":

```
python manage.py gc_inspect myapp.Attachment 42
```

The model must be configured for garbage collection. The reported status is
one of:

- *object not found* — no row with that primary key exists.
- *object excluded by filter* — the row exists but the model's `gc_filter`
  excludes it, so it is not currently a deletion candidate (a time-based
  filter may still let it through later).
- *object referenced by N other objects* — the row is still referenced by
  foreign keys (each referencing `model.field (pk=...)` is listed), so it is
  retained.
- *object is unreferenced and would be collected* — the row passes the filter
  and nothing references it, so a `gc --delete` run would remove it.

A typical deployment runs it from a daily cron job:

```
0 0 * * * python manage.py gc --delete
```

## Caveats

- Only `ForeignKey` references are considered. Rows referenced solely through
  `ManyToManyField` or generic foreign keys are treated as unreferenced, so
  don't enable garbage collection for models referenced that way.
- Deletions go through the ORM (`QuerySet.delete()`), so `on_delete` behavior
  and signals fire as usual.
- Rows created while a batch is being processed can be referenced-yet-deleted
  only if a referencing row is written without the referenced row being
  visible in the batch's transaction; give new rows a grace period with
  `gc_filter` if creation of the target and the reference is not atomic.

## Development

```
pip install -e '.[test]'
pytest
```
