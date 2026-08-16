from apps.metering.pricing.models import Rate, RateCard
from apps.platform.event_types.tests._helpers import declares_a_quantity

#: WHICH QUANTITY A RATE PRICES WHEN THE FIXTURE NEVER SAID (#326).
#:
#: Most callers here name one; the ones that do not are asking for "a rate" and
#: are about something else entirely — an effective moment, a book, a slot. They
#: used to get the empty string, which is not a name any event carries, so their
#: rate matched nothing and that was invisible and harmless. It is no longer
#: writable: a rate names a DECLARED quantity and "" is not one. This is the
#: same nothing, said out loud — a real declaration, under a name no event in
#: this repository measures, so those fixtures keep resolving exactly as they
#: did rather than quietly starting to match a posting.
UNMEASURED_QUANTITY = "a_quantity_no_event_measures"


def rate_in_default_book(tenant, *, card_type="price", provider="", event_type="",
                         task_type="", subtask_type="",
                         customer=None, **fields):
    """Create a Rate attached to the tenant's is_default book for its
    (card_type, provider, currency). If customer is given, attach to a
    customer book + assignment instead. Mirrors the backfill's grouping so
    tests exercise the real resolution path.

    **A CALLER STILL SAYS `measurement_key=` AND STILL NEVER SEES A COLUMN
    (#326).** The rate holds the declared record now, so the name is resolved to
    the declaration here — and declared, once, if the tenant has not declared it
    already. That keeps every fixture in the tree saying what it means rather
    than transcribing a two-record setup, and it is why the reference conversion
    did not have to touch them: what they ask for has not changed, only what it
    takes to be true. A test that wants a rate NOT backed by a declaration wants
    the refusal, and asks for it explicitly."""
    from apps.metering.pricing.models import RateCardAssignment
    currency = fields.get("currency", tenant.default_currency or "usd")
    if customer is None:
        book, _ = RateCard.objects.get_or_create(
            tenant=tenant, card_type=card_type, provider_key=provider, currency=currency,
            is_default=True, defaults={"key": (provider or "default")[:64]})
    else:
        book, _ = RateCard.objects.get_or_create(
            tenant=tenant, card_type=card_type, key=f"cust-{customer.id}-{currency}"[:64],
            defaults={"provider_key": provider, "currency": currency})
        if card_type == "price":
            RateCardAssignment.objects.get_or_create(
                tenant=tenant, customer=customer, currency=currency,
                defaults={"rate_card": book})
    if "measurement" not in fields:
        fields["measurement"] = declares_a_quantity(
            tenant, fields.pop("measurement_key", UNMEASURED_QUANTITY))
    # The slots ride in **fields rather than being named one by one. Ten of them
    # spelled out as keyword defaults was already the longest line in this file
    # at six, and every one of them would have been ``slot=slot`` — the model's
    # own "" default says the same thing without the transcription.
    return Rate.objects.create(tenant=tenant, card_type=card_type, provider=provider,
                               event_type=event_type, task_type=task_type,
                               subtask_type=subtask_type,
                               customer=customer, rate_card=book,
                               book_version_from=book.version, **fields)


def cost_book(tenant, *, key="default", provider="", currency="usd"):
    """A COST book with no rates in it, for a test that adds its own.

    Here for the same reason `cost_rate_in_default_book` below is: the word that
    separates a cost book from a price one is retired, slice 4 owns re-spelling
    it, and the ledger caps how many files may still contain it. A test that
    wanted an empty book to post rates into had to spell it — this file already
    carries the word, so it spells it once and callers say what they mean.
    """
    return RateCard.objects.create(
        tenant=tenant, card_type="cost", key=key, provider_key=provider,
        currency=currency, is_default=True)


def cost_rate_in_default_book(tenant, **fields):
    """A COST Rate, without the caller having to name the discriminator.

    The word that separates a cost rate from a price rate is retired and slice 4
    owns re-spelling it (`pricing/models.py:50`), so the migration ledger caps
    how many files may still contain it. That cap is a ceiling on SPREAD, not
    only on what is left to fix — a new test module that names it puts the count
    over its entry and the sweep fails. This file is already one of the counted
    ones, so the word stays here and callers say what they mean.
    """
    return rate_in_default_book(tenant, card_type="cost", **fields)
