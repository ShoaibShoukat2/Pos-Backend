import uuid

from django.db import models


class UUIDModel(models.Model):
    """UUID primary keys keep future offline sync (Module 19) conflict-free."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class BusinessScopedQuerySet(models.QuerySet):
    def for_business(self, business):
        return self.filter(business=business)


class BusinessScopedManager(models.Manager.from_queryset(BusinessScopedQuerySet)):
    pass


class DocumentSequence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="document_sequences",
    )
    key = models.CharField(max_length=20)
    prefix = models.CharField(max_length=12)
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=6)

    class Meta:
        unique_together = ("business", "key")

    def __str__(self):
        return f"{self.business_id} {self.key}"
