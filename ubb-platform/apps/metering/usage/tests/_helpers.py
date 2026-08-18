"""Shared scaffolding for the posting table's declared-transition modules.

ADR-0007 §2 names three doors — `save()`, `QuerySet.update()` and raw SQL — and
requires every declared transition to hold across all of them. That is a
statement about the TABLE rather than about either pair declared on it, so the
doors, the committed-posting fixture and the refusal assertion live here, and
both trio modules use them: `test_a_cost_settles_once.py` for the supplier pair
(#318) and `test_a_price_resolves_once.py` for the customer price pair (#352).

`docs/conventions/testing.md` asks for exactly this — shared setup helpers in
`tests/_helpers.py` rather than tenants and customers re-scaffolded by hand.
The second trio is what made the duplication real rather than hypothetical, and
the first draft of #352 copied all of it across with a note arguing that sharing
would let either file's deletion take both trios down. That argument does not
survive contact with an import: deleting this module breaks both trios loudly,
at collection, which is the opposite of the silent failure it worried about.

**⚠ THE REFUSAL ASSERTION NAMES A COLUMN, AND THAT IS THE POINT OF IT.** Both
pairs on this table are declared `RESOLVE_ONCE`, so **both** triggers raise a
message carrying that token — asserting the transition class alone cannot tell
one rule's refusal from the other's, and a trio that did so would be evidence
about "this table refuses things" rather than about its own rule. Each test
class states the column its refusals must name, and `_refused_by_the_trigger`
refuses to run without one. There is deliberately **no default**: a default
would be the vacuous version of this check, and the check is the one thing a
shared helper could quietly stop doing for every caller at once.
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
# every prohibited transition in both trio modules is driven through all three.

def through_the_queryset(posting, **columns):
    Posting.objects.filter(pk=posting.pk).update(**columns)


def through_raw_sql(posting, **columns):
    assignments = ", ".join(f"{name} = %s" for name in columns)
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s",
                       [*columns.values(), str(posting.pk)])


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
            "transition class cannot tell this table's two rules apart")
        for name, door in DOORS:
            with self.subTest(door=name):
                message = self._refusal(door, posting_factory(), **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(transition_class, message)
                self.assertIn(self.REFUSAL_NAMES, message)
