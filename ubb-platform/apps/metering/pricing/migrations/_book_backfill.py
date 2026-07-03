"""Backfill logic for 0012. Groups active Rates into books.

Default (customer IS NULL) rates -> one is_default book per
(tenant, card_type, provider, currency), named after the provider.
Customer-scoped rates -> a per-(customer, card_type) book + a price-book
assignment. Only ACTIVE rates (valid_to IS NULL) are grouped; historical
versions inherit their lineage sibling's book in a second pass.
"""


def _book_for(RateCard, tenant_id, card_type, provider, currency, customer_id):
    is_default = customer_id is None
    key = (provider or "default") if is_default else f"cust-{customer_id}-{provider or 'default'}"
    book, _ = RateCard.objects.get_or_create(
        tenant_id=tenant_id, card_type=card_type, key=key[:64],
        defaults={"provider_key": provider or "", "currency": currency,
                  "name": provider or "default", "version": 1,
                  "is_default": is_default},
    )
    return book


def forwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")

    # Pass 1: active rates -> books.
    for r in Rate.objects.filter(valid_to__isnull=True, rate_card__isnull=True):
        customer_id = r.customer_id
        book = _book_for(RateCard, r.tenant_id, r.card_type, r.provider,
                         r.currency, customer_id)
        r.rate_card = book
        r.book_version_from = 1
        r.book_version_to = None
        r.save(update_fields=["rate_card", "book_version_from", "book_version_to"])
        if customer_id is not None and r.card_type == "price":
            RateCardAssignment.objects.get_or_create(
                tenant_id=r.tenant_id, customer_id=customer_id, currency=r.currency,
                defaults={"rate_card": book})

    # Pass 2: historical rate versions -> same book as their active lineage sibling.
    active_by_lineage = {
        r.lineage_id: r.rate_card_id
        for r in Rate.objects.filter(valid_to__isnull=True)
    }
    for r in Rate.objects.filter(rate_card__isnull=True):
        book_id = active_by_lineage.get(r.lineage_id)
        if book_id is None:
            # No active sibling (fully superseded lineage): give it its own book.
            book = _book_for(RateCard, r.tenant_id, r.card_type, r.provider,
                             r.currency, r.customer_id)
            book_id = book.id
        r.rate_card_id = book_id
        r.save(update_fields=["rate_card"])


def backwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")
    Rate.objects.update(rate_card=None)
    RateCardAssignment.objects.all().delete()
    RateCard.objects.all().delete()
