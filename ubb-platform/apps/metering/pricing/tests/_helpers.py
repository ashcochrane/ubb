from uuid import uuid4

from django.db import IntegrityError, connection, transaction

from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.receipts import ReceiptSubject
from apps.metering.usage.models import Posting
from apps.platform.event_types.tests._helpers import declares_a_quantity
from core.vocabulary import PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT

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


def a_usage_event_subject(subject_id=None):
    """A receipt subject for a test whose question is resolution, not identity.

    `PricingService.price` requires its subject and gives it no default (#349):
    a receipt explains one named thing, and a default would hand one subject's
    answer to every caller who left the argument out. The tests that resolve a
    price are almost all about WHAT was resolved rather than about which row it
    was resolved for, so they say that here once instead of each inventing an
    id. A test that IS about the identity passes its own.
    """
    return ReceiptSubject(
        subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
        subject_id=str(subject_id or uuid4()))


def receipt_without_its_per_event_facts(body):
    """A recording result whose receipt can be compared with another's (#349).

    Two parity tests ask whether two recordings produced the SAME body — the
    batch endpoint against the single one, and a recording with a declared
    grouping against one without. The Pricing Receipt names the row it explains
    and the instant it resolved as of, and both are per-event by construction,
    exactly as the event id beside them always was. Masking them is the only way
    those questions stay askable.

    **Everything else in the record is left alone deliberately**, because it is
    where the parity actually bites: both methods, both statuses, the components
    and the totals must still match byte for byte.

    Lives here rather than in either caller because it was written twice before
    it was written once, and the second copy is what put the receipt column's
    retired spelling over its ceiling — a helper is also the answer to that,
    since it addresses the column through the model's own constant in one place.
    """
    return {**body, Posting.RECEIPT_COLUMN: {
        **body[Posting.RECEIPT_COLUMN],
        "subject_id": "SUBJECT", "effective_at": "AS_OF"}}


# --- The three doors ADR-0007 §2 names, over one rule -------------------------
#
# A guard only one door respects is the defect a database rule exists to catch,
# so every prohibited write against this table is driven through all three.
# `usage/tests/_helpers.py` has the same three over a posting, and the two sets
# are not one set: they write different columns on different tables through
# different model APIs, and the only lines they would share are the two the ORM
# dictates. What IS copied is the structure, which is what "copy the prior art"
# means.

def through_the_queryset(rule, **columns):
    Rate.objects.filter(pk=rule.pk).update(**columns)


def through_raw_sql(rule, **columns):
    """Raw SQL, with each value prepared the way its own column takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_value` is the
    model field's own answer to what the driver should be handed, so this door
    writes exactly what the ORM writes and differs from the other two only in
    going around them — which is the whole point of it.
    """
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [Rate._meta.get_field(name).get_db_prep_value(value, connection)
              for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {Rate._meta.db_table} SET {assignments} WHERE id = %s",
            [*values, str(rule.pk)])


def through_save(rule, **columns):
    """`save()` — the door a shell session, a data migration or a fixture uses."""
    for name, value in columns.items():
        setattr(rule, name, value)
    rule.save()


DOORS = (("QuerySet.update()", through_the_queryset),
         ("raw SQL", through_raw_sql),
         ("save()", through_save))


class RuleRefusalThroughEveryDoorMixin:
    """Every prohibited write against a rule, driven through all three doors.

    ⚠ `REFUSAL_NAME` has no default on purpose. Several mechanisms on this table
    answer `IntegrityError` and two of them now refuse writes to the same
    column, so a subclass that forgot to say which one it is about would assert
    against whatever the base class happened to carry — the shape that let a
    rule refusing the wrong thing pass its own check one slice ago.
    """

    #: The constraint a subclass's refusals must name. Set per class.
    REFUSAL_NAME = None

    def assert_every_door_refuses(self, rule, **columns):
        self.assertIsNotNone(
            self.REFUSAL_NAME,
            "this class has not said which mechanism its refusals belong to")
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaisesRegex(IntegrityError, self.REFUSAL_NAME):
                    with transaction.atomic():
                        door(rule, **columns)
                rule.refresh_from_db()
