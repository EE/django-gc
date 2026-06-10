from django.db import models


class Document(models.Model):
    """Garbage collected when no Reference points to it."""

    gc_enabled = True

    created_at = models.DateTimeField(auto_now_add=True)


class Reference(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)


class Cache(models.Model):
    """Garbage collected even while CacheLog rows point at it."""

    gc_enabled = True
    gc_ignored_referencing_fields = ['testapp.CacheLog.cache']


class CacheLog(models.Model):
    cache = models.ForeignKey(Cache, on_delete=models.CASCADE)
