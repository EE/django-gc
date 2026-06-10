from django.db import models


class Document(models.Model):
    """Garbage collected when no Reference points to it."""

    gc_enabled = True

    created_at = models.DateTimeField(auto_now_add=True)


class Reference(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
