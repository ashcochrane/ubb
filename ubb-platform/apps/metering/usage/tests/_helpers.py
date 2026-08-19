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

**It also carries the one way a test may now remove a measurement record**
(#354). That is a rule of the CHILD table rather than of this one, and its doors
are `delete()`, `QuerySet.delete()` and raw SQL rather than the three below —
its own module owns those. What is here is `release_the_horizon`, which is the
**only** write of `prunable_at` after insert anywhere in the tree, and
`release_and_prune` over it. Three modules prune and a fourth releases without
pruning; each one inventing that for itself is four chances to invent a
different prune, and one of them would have been a second writer of a column
this record's declared rule says is never rewritten.

**The two catalogue queries take a table** for the same reason: the child's rule
has to ask the same questions of `ubb_posting_measurement` that the three trios
ask of `ubb_posting`, and a second copy of one search would only ever prove that
two copies of a search agree with each other.

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
from datetime import timedelta

from django.db import IntegrityError, connection, models, transaction
from django.utils import timezone

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


def settle_the_supplier_cost(posting, micros):
    """Settle an unresolved supplier cost — through the one production door.

    `pricing.services.cost_settlement.settle_provider_cost` is *the* application
    writer of a cost resolution, and a gate walks living backend code to keep it
    that way. A test helper re-issuing the same `UPDATE` by hand would be a
    second writer wearing a fixture's clothes: it would miss the conditional
    `WHERE` clause that makes the move safe under a race, and it would keep
    passing on the day that door changed. So this calls it and asserts what it
    answers, rather than reproducing it.

    It is here because #354 made *resolving* the thing that releases a
    measurement record, and three modules now need that sequence. ⚠ **The
    recording path produces `unresolved` far more often than it looks**: a
    metered call whose quantity has no cost rate lands there, which is most
    fixtures, so `release_and_prune` on a freshly recorded posting is refused
    for the second condition rather than the first.
    """
    from apps.metering.pricing.services.cost_settlement import (
        Settlement, settle_provider_cost)

    outcome = settle_provider_cost(posting_id=posting.pk,
                                   provider_cost_micros=micros)
    assert outcome is Settlement.SETTLED, outcome
    return outcome


def release_the_horizon(posting):
    """Put a posting's measurement record past its `prunable_at`.

    ⚠ **THE ONLY PLACE IN THE TREE THAT WRITES THIS COLUMN AFTER INSERT**, and
    it walks through a hole #354 does not close. The record's declared lifecycle
    says *no column is ever rewritten*, and that line has no enforcement behind
    it; `prunable_at` meanwhile has no clock, no job and no owner, so nothing in
    production ever sets it and a test standing a row up as *released* has no
    other way in. Confining it to one function is what makes that sentence
    checkable — and the day a later slice enforces the `UPDATE` line, this is
    the single thing that has to change.

    Separate from `release_and_prune` because a caller sweeping two records in
    one `DELETE` needs the release without the removal, and inlining the
    `UPDATE` there would have put a second writer of this column in the tree on
    the same commit that claimed there was one.
    """
    from apps.metering.usage.models import PostingMeasurement

    return PostingMeasurement.objects.filter(posting=posting).update(
        prunable_at=timezone.now() - timedelta(days=1))


def release_and_prune(posting):
    """Remove a posting's measurement record the way a prune has to, since #354.

    The child's whole-record rule permits a `DELETE` only at or after the
    record's `prunable_at` and only while its posting is not unresolved, and the
    database holds it. So a test that wants the state a prune leaves has to
    reach it legally, and this is where that is spelled — rather than at each
    call site, every one of them free to drift into a different idea of what a
    prune is.

    The caller keeps responsibility for the second condition. A posting still
    carrying `unresolved` or `unknown` is refused here exactly as it would be
    anywhere else, and that refusal is a fact worth a test rather than
    something for a helper to paper over.
    """
    from apps.metering.usage.models import PostingMeasurement

    release_the_horizon(posting)
    return PostingMeasurement.objects.filter(posting=posting).delete()


def rules_on_the_table(table=TABLE):
    """Every non-internal trigger on one table, as a SET of names.

    The catalogue query, shared; the SET each module compares it against is
    not — see this module's docstring. Names rather than a count, because
    `pg_trigger` promises no order and a count that was merely bumped survives
    one rule being dropped while another arrives.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [table])
        return {name for (name,) in cursor.fetchall()}


def rule_on_the_table(trigger, table=TABLE):
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
            "WHERE c.relname = %s AND t.tgname = %s", [table, trigger])
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
