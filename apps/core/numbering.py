from django.db import transaction

from apps.core.models import DocumentSequence


@transaction.atomic
def allocate_number(business, key: str, prefix: str, padding: int = 6) -> str:
    seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
        business=business,
        key=key,
        defaults={"prefix": prefix, "padding": padding},
    )
    number = f"{seq.prefix}-{str(seq.next_number).zfill(seq.padding)}"
    seq.next_number += 1
    seq.save(update_fields=["next_number"])
    return number
