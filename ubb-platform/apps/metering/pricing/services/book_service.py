from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, validate_tiers

_RATE_COPY_FIELDS = (
    "tenant_id", "customer_id", "card_type", "provider", "event_type",
    "metric_name", "dimensions", "pricing_model", "rate_per_unit_micros",
    "unit_quantity", "fixed_micros", "tiers", "currency", "product_id",
    "lineage_id", "rate_card_id",
)


class BookService:
    @staticmethod
    def publish(book, changes, as_of=None):
        """Atomically reprice a set of the book's rates. Each change must match
        exactly one ACTIVE rate in the book by (metric_name, provider,
        event_type, dimensions). Supersedes it (valid_to=T, book_version_to=old
        version) and inserts a new active rate (same lineage_id, valid_from>=T,
        book_version_from=new version). Bumps book.version once. All-or-nothing.

        `as_of` is expected to be ~now (used for the supersede timestamp);
        future-dated scheduling is not supported because the new rate's
        valid_from is auto-stamped at insert.
        """
        as_of = as_of or timezone.now()
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=book.id)
            new_version = locked.version + 1
            for ch in changes:
                old = Rate.objects.select_for_update().filter(
                    rate_card=locked, valid_to__isnull=True,
                    metric_name=ch["metric_name"],
                    provider=ch.get("provider", ""),
                    event_type=ch.get("event_type", ""),
                ).filter(Q(dimensions=ch.get("dimensions", {}))).first()
                if old is None:
                    raise ValueError(
                        f"publish: no active rate for {ch['metric_name']!r} in book {locked.key}")
                data = {f: getattr(old, f) for f in _RATE_COPY_FIELDS}
                for k in ("pricing_model", "rate_per_unit_micros", "unit_quantity",
                          "fixed_micros", "tiers"):
                    if k in ch:
                        data[k] = ch[k]
                data["book_version_from"] = new_version
                data["book_version_to"] = None
                # Re-validate the repriced shape so a publish can never create an
                # invalid tiered rate (e.g. graduated with empty tiers). Raises
                # ValueError -> rolls back the whole publish (endpoint maps 422).
                validate_tiers(data["card_type"], data["pricing_model"], data["tiers"])
                # Close the old row, then open the new (valid_from auto_now_add > T).
                old.valid_to = as_of
                old.book_version_to = locked.version
                old.save(update_fields=["valid_to", "book_version_to", "updated_at"])
                Rate.objects.create(**data)
            locked.version = new_version
            locked.save(update_fields=["version", "updated_at"])
            book.version = new_version
            return book
