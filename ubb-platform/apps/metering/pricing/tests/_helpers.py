from uuid import uuid4

from django.db import IntegrityError, connection, transaction

from apps.metering.pricing.models import Rate, RateCard, TenantDefaultMarkup
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


def the_book_holding(rule):
    """The book a rule lives in.

    A one-line reader, and it earns its place for the reason `cost_book` above
    does: the column that points a rule at its container is retired, its ledger
    entry is a ceiling on how many files may still spell it, and a test whose
    subject is the book — publishing it, diffing it — needs the object rather
    than the column name. This file already carries the word.
    """
    return rule.rate_card


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


def rate_in_the_providers_default_book(tenant, provider, **fields):
    """A rule in the tenant's default book FOR ONE PROVIDER, pinning nothing.

    `rate_in_default_book` takes one `provider` and uses it twice — it selects
    the book AND pins the rule's own selector — which is what almost every
    fixture here wants. This separates the two, and there is exactly one
    question that needs them separated: whether two rules in two DIFFERENT
    default books can be made equally specific. They can only be if neither
    pins the provider, which `rate_in_default_book` cannot express.

    The book discriminator is spelled here like every other book construction
    in this file, so a caller asking about ranking never has to.
    """
    book, _ = RateCard.objects.get_or_create(
        tenant=tenant, card_type="price", provider_key=provider,
        currency=fields.get("currency", tenant.default_currency or "usd"),
        is_default=True, defaults={"key": provider[:64]})
    if "measurement" not in fields:
        fields["measurement"] = declares_a_quantity(
            tenant, fields.pop("measurement_key", UNMEASURED_QUANTITY))
    return Rate.objects.create(
        tenant=tenant, card_type="price", rate_card=book,
        book_version_from=book.version, **fields)


def declares_a_markup(tenant, *, percentage_micros=0):
    """The markup rung a tenant has to declare before a price can settle (#356).

    **THE DEFAULT IS ZERO, AND ZERO IS A DECISION.** A tenant with a rung of
    nothing is saying *charge my customer what the call cost*, which settles at
    the supplier's figure and is what the fixtures using this helper always
    meant. What they used to rely on was the absence of a rung producing the
    same number, and that stopped being true when a price nobody stated became
    `unknown` rather than the cost. The distinction is the whole point: an
    absent rung is not a zero rung.

    Named for the act rather than the record — a tenant declares a markup, and
    which row carries it is this module's business, not its callers'. **That is
    what let the record change underneath every caller in #357**: the rung moved
    off the customer-override table's `customer IS NULL` row and onto a record
    of its own, and no fixture in the tree had to say so.

    ⚠ **THE TENANT DEFAULT ONLY, WHICH IT ALWAYS WAS.** It used to take a
    `customer=` and no caller ever passed one; the rung it now writes is the
    tenant's by construction, so the argument is gone rather than accepting a
    value it would have to ignore. A customer-level override is a different rung
    and a test that wants one asks for it by name.
    """
    return TenantDefaultMarkup.objects.create(
        tenant=tenant, markup_micro_percent=percentage_micros)


def markup_terms(basis_micros, *, micro_percent=0, fixed_uplift_micros=0):
    """The terms a `margin_over_cost` price must carry on its receipt (#357).

    `build_receipt` refuses a margin that arrives without them, so every fixture
    building a settled `margin_over_cost` resolution by hand needs a set — and
    two modules in two apps do, which is why this is here rather than copied
    into each. `docs/conventions/testing.md` puts shared setup in a `_helpers`
    module for exactly the reason that applies: a second copy is a second thing
    to edit the day `REQUIRED_MARKUP_KEYS` moves, and the day one of them is
    missed is the day a fixture asserts a shape the boundary no longer accepts.

    **THE DEFAULTS MAKE THE ARITHMETIC TRUE, WHICH IS THE POINT OF A DEFAULT
    HERE.** A rung of zero over a basis of `basis_micros` IS `basis_micros`, so
    a caller who names only the basis gets terms that reproduce their own
    amount rather than three numbers that merely sit beside it. A caller taking
    a real percentage says so and states the amount it produces itself.
    """
    return {"micro_percent": micro_percent,
            "fixed_uplift_micros": fixed_uplift_micros,
            "basis_micros": basis_micros}


def rate_in_a_book_nothing_selects(tenant, *, key="unselected", provider="",
                                   currency="usd", **fields):
    """A price rule in a book resolution never reads (#356).

    A book becomes readable in exactly two ways — it is the tenant's default for
    the event's provider, or a customer is assigned to it — and this is neither.
    It exists so that "there is no fallthrough between books" can be asserted by
    a rule that WOULD match the event on every selector and is still not the
    answer, rather than by the absence of a rule, which proves nothing about
    reachability.

    The discriminator that separates a price book from a cost one is retired and
    its ledger entry is a ceiling on how many files may still spell it, so it is
    spelled here — beside every other book construction in this file — and
    callers say what they mean.
    """
    book = RateCard.objects.create(
        tenant=tenant, card_type="price", key=key, provider_key=provider,
        currency=currency, is_default=False)
    if "measurement" not in fields:
        fields["measurement"] = declares_a_quantity(
            tenant, fields.pop("measurement_key", UNMEASURED_QUANTITY))
    return Rate.objects.create(
        tenant=tenant, card_type="price", provider=provider, currency=currency,
        rate_card=book, book_version_from=book.version, **fields)


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


# --- The three doors ADR-0007 §2 names, over one record ----------------------
#
# A guard only one door respects is the defect a database rule exists to catch,
# so every prohibited write against this app's tables is driven through all
# three. `usage/tests/_helpers.py` has the same three over a posting, and the
# two sets are not one set: they write different columns on different tables
# through different model APIs, and the only lines they would share are the two
# the ORM dictates. What IS copied is the structure, which is what "copy the
# prior art" means.
#
# THE RECORD DECIDES ITS OWN MODEL, WHICH IS WHY THESE THREE TAKE NO MODEL
# ARGUMENT AND NAME NONE (#358). A second rule landed on a second table in this
# app — a publish record, whose whole-record rule needs the same three doors as
# the rule table's column rules — and a copy of these functions differing only
# in a class name would be the duplication `docs/conventions/testing.md` puts a
# `_helpers` module here to prevent.

def through_the_queryset(record, **columns):
    type(record).objects.filter(pk=record.pk).update(**columns)


def through_raw_sql(record, **columns):
    """Raw SQL, with each value prepared the way its own column takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_value` is the
    model field's own answer to what the driver should be handed, so this door
    writes exactly what the ORM writes and differs from the other two only in
    going around them — which is the whole point of it.
    """
    model = type(record)
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [model._meta.get_field(name).get_db_prep_value(value, connection)
              for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {model._meta.db_table} SET {assignments} WHERE id = %s",
            [*values, str(record.pk)])


def through_save(record, **columns):
    """`save()` — the door a shell session, a data migration or a fixture uses."""
    for name, value in columns.items():
        setattr(record, name, value)
    record.save()


DOORS = (("QuerySet.update()", through_the_queryset),
         ("raw SQL", through_raw_sql),
         ("save()", through_save))


class RefusalThroughEveryDoorMixin:
    """Every prohibited write against a record, driven through all three doors.

    ⚠ `REFUSAL_NAME` has no default on purpose. Several mechanisms on these
    tables answer `IntegrityError` and two of them refuse writes to the same
    column, so a subclass that forgot to say which one it is about would assert
    against whatever the base class happened to carry — the shape that let a
    rule refusing the wrong thing pass its own check one slice ago.
    """

    #: The constraint a subclass's refusals must name. Set per class.
    REFUSAL_NAME = None

    def assert_every_door_refuses(self, record, **columns):
        self.assertIsNotNone(
            self.REFUSAL_NAME,
            "this class has not said which mechanism its refusals belong to")
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaisesRegex(IntegrityError, self.REFUSAL_NAME):
                    with transaction.atomic():
                        door(record, **columns)
                record.refresh_from_db()
