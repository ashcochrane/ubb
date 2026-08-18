"""Shared scaffolding for the posting table's declared-transition modules.

ADR-0007 §2 names three doors — `save()`, `QuerySet.update()` and raw SQL — and
requires every declared transition to hold across all of them. That is a
statement about the TABLE rather than about any one thing declared on it, so the
doors, the committed-posting fixture, the refusal assertion and the two
catalogue queries live here, and all three trio modules use them:
`test_a_cost_settles_once.py` for the supplier pair (#318),
`test_a_price_resolves_once.py` for the customer price pair (#352) and
`test_a_receipt_seals_once_it_is_complete.py` for the receipt (#353).

⚠ **What is shared is how a question is ASKED, never the answer.** Each module
still spells the table's rule set out for itself and asserts it by equality: an
assertion every module took from one place could be satisfied by editing that
place, and the whole job of that line is to make a rule's arrival on this table
something a reader of each module has to agree to.

`docs/conventions/testing.md` asks for exactly this — shared setup helpers in
`tests/_helpers.py` rather than tenants and customers re-scaffolded by hand.
The second trio is what made the duplication real rather than hypothetical, and
the first draft of #352 copied all of it across with a note arguing that sharing
would let either file's deletion take both trios down. That argument does not
survive contact with an import: deleting this module breaks every trio loudly,
at collection, which is the opposite of the silent failure it worried about.

**⚠ THE REFUSAL ASSERTION NAMES A COLUMN, AND THAT IS THE POINT OF IT.** All
three of this table's declarations are `RESOLVE_ONCE`, so **every** trigger on
it raises a message carrying that token — asserting the transition class alone
cannot tell one rule's refusal from another's, and a trio that did so would be
evidence about "this table refuses things" rather than about its own rule. Each
test class states the column its refusals must name, and
`_refused_by_the_trigger` refuses to run without one. There is deliberately **no
default**: a default would be the vacuous version of this check, and the check
is the one thing a shared helper could quietly stop doing for every caller at
once.
"""
from django.db import IntegrityError, connection, models, transaction

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

TABLE = Posting._meta.db_table


def committed_posting(**columns):
    """A committed posting, each with a tenant and customer of its own."""
    tenant = Tenant.objects.create(name="T")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    columns.setdefault("idempotency_key", "k")
    return Posting.objects.create(tenant=tenant, customer=customer, **columns)


# --- The three doors ADR-0007 §2 names, each writing the same columns --------
#
# A guard only one of them respects is the defect the rule exists to catch, so
# every prohibited transition in all three trio modules is driven through all
# three of them.

def through_the_queryset(posting, **columns):
    Posting.objects.filter(pk=posting.pk).update(**columns)


def through_raw_sql(posting, **columns):
    """Raw SQL, with each value prepared the way its own column takes it.

    The door is *raw SQL*, not *raw Python objects*. A scalar column needs
    nothing doing to it and the first two trios never noticed this line; a
    `jsonb` column does, because handing the driver a `dict` asks it to guess a
    type the column has already declared, and it refuses rather than guessing.
    `get_db_prep_value` is the model field's own answer to that question, so
    this door writes exactly what the ORM writes and differs from the other two
    only in going around them — which is the whole point of it.
    """
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [Posting._meta.get_field(name).get_db_prep_value(
                  value, connection) for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s",
                       [*values, str(posting.pk)])


def through_save(posting, **columns):
    """`save()`, reaching around the model's own refusal on the way.

    `Posting.save()` raises on any update, so a plain `save()` never reaches the
    database and would prove nothing about it. Calling the base implementation is
    what a writer that bypasses the override looks like — a `bulk_update`, a data
    migration, a shell session — and it is the door ADR-0007 §2 means.
    """
    for name, value in columns.items():
        setattr(posting, name, value)
    models.Model.save(posting)


DOORS = (("QuerySet.update()", through_the_queryset),
         ("raw SQL", through_raw_sql),
         ("save()", through_save))


def rules_on_the_table():
    """Every non-internal trigger on the posting table, as a SET of names.

    The catalogue query, shared; the SET each module compares it against is
    not — see this module's docstring. Names rather than a count, because
    `pg_trigger` promises no order and a count that was merely bumped survives
    one rule being dropped while another arrives.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
        return {name for (name,) in cursor.fetchall()}


def rule_on_the_table(trigger):
    """One rule's `(tgtype, prosrc)`, asked for BY NAME, or `None`.

    By name and never by index: with three rules on this table, anything
    reading "the first row" is reading whichever one Postgres happened to hand
    back. `None` where the rule is absent, so a reversed-out migration is an
    assertable state rather than an exception from the middle of a test.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgtype, p.prosrc FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE c.relname = %s AND t.tgname = %s", [TABLE, trigger])
        return cursor.fetchone()


class TransitionRefusalMixin:
    """Drive a prohibited write through all three doors and read the refusal."""

    #: The column this class's refusals must NAME, beside the transition class.
    #: Set it per test class; see this module's docstring for why there is no
    #: default and why the transition class alone is not enough.
    REFUSAL_NAMES = None

    def _refusal(self, door, posting, **columns):
        """The message Postgres refused with, or `None` if it did not refuse."""
        try:
            with transaction.atomic():
                door(posting, **columns)
        except IntegrityError as refusal:
            return str(refusal)
        return None

    def _refused_by_the_trigger(self, posting_factory, transition_class,
                                **columns):
        self.assertIsNotNone(
            self.REFUSAL_NAMES,
            "set REFUSAL_NAMES on this class: a refusal that names only the "
            "transition class cannot tell this table's rules apart")
        for name, door in DOORS:
            with self.subTest(door=name):
                message = self._refusal(door, posting_factory(), **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(transition_class, message)
                self.assertIn(self.REFUSAL_NAMES, message)
