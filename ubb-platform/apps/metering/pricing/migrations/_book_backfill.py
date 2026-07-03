"""Backfill logic for 0012. Groups active Rates into books.

Default (customer IS NULL) rates -> one is_default book per
(tenant, card_type, provider, currency), named after the provider.
Customer-scoped rates -> a per-(customer, card_type) book + a price-book
assignment. Only ACTIVE rates (valid_to IS NULL) are grouped; historical
versions inherit their lineage sibling's book in a second pass.
"""


def _book_for(RateCard, tenant_id, card_type, provider, currency, customer_id):
    """Resolve-or-create the book a rate belongs to. The natural key
    (tenant, card_type, key) must encode everything that distinguishes a book,
    so `key` includes `currency` (default books are per
    (tenant, card_type, provider, currency)). Customer books are per
    (customer, currency) and SPAN providers (matching the one-assignment-
    per-(customer, currency) model), so provider is NOT in the customer key and
    provider_key stays "" (the is_default partial-unique does not apply to
    non-default books; resolution filters rates within the book by
    Rate.provider, so a provider-spanning customer book resolves fine)."""
    is_default = customer_id is None
    if is_default:
        key = f"{provider or 'default'}-{currency}"
        provider_key, name = provider or "", provider or "default"
    else:
        key = f"cust-{customer_id}-{currency}"
        provider_key, name = "", "custom"
    book, _ = RateCard.objects.get_or_create(
        tenant_id=tenant_id, card_type=card_type, key=key[:64],
        defaults={"provider_key": provider_key, "currency": currency,
                  "name": name, "version": 1, "is_default": is_default},
    )
    return book


def forwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")

    # Guard (design §6): customer-scoped COST rates have no book resolution path
    # (cost books are not assignable), so backfilling them would silently drop the
    # customer's cost basis. Fail loudly so a human resolves them first.
    orphan_cost = Rate.objects.filter(
        card_type="cost", customer__isnull=False, valid_to__isnull=True).count()
    if orphan_cost:
        raise RuntimeError(
            f"{orphan_cost} active customer-scoped cost rate(s) have no book "
            "resolution path; resolve these before backfilling (design §6).")

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

    # Parity: every active rate must now belong to exactly one book.
    orphaned = Rate.objects.filter(valid_to__isnull=True, rate_card__isnull=True).count()
    if orphaned:
        raise RuntimeError(f"backfill parity failure: {orphaned} active rate(s) without a book")


def backwards(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    RateCardAssignment = apps.get_model("pricing", "RateCardAssignment")
    Rate.objects.update(rate_card=None)
    RateCardAssignment.objects.all().delete()
    RateCard.objects.all().delete()
