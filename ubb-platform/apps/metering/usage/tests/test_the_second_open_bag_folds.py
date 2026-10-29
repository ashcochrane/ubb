"""The second open bag folded into the first, and only the first survives (#273).

A posting carries ONE open bag, `metadata`: filterable and readable, never
groupable. The second bag, whose name implied the grouping capability the first
deliberately does not have, is gone from the model and from the table, and the
survivor keeps the GIN index its filters need. `TheSecondBagIsGoneTest` holds
that end state.

`TheBagIsNotAGroupingAxisTest` at the foot carries the other half of the
ticket, and states exactly how far it reaches.

Before the cutover (#190) this module also ran the FOLD: `usage/0033`'s
operation order (the data moved before the column went, ADR-0007 §1) and its
forward and reverse callables against a real table — every key surviving, a
disagreeing key refused rather than a winner picked, and a reverse that gave
both bags the merged contents so the round trip was total. Those were facts
about one migration's data step, and they retired with the chain.
"""

from django.db import connection
from django.test import TestCase

from api.v1.tests._helpers import retired_aliases
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import a_posting

#: The retired bag, READ OFF THE REGISTRY RATHER THAN SPELLED HERE.
#:
#: The forbidden-term sweep refuses a living file that names a retired word, so
#: the one honest source is the document that retired it — `retired.yaml`'s
#: `metadata_key`, whose `retired_aliases` is that bag's name. Until the cutover
#: (#190) it was read off `usage/0033`'s `RemoveField`; that migration is gone,
#: and the registry is the source that outlives it.
#: Unpacked from a one-element tuple on purpose: a registry entry that ever grew
#: a second alias would make `next(...)` pick one silently, and every assertion
#: below would then be about a column nobody meant.
(RETIRED_COLUMN,) = tuple(retired_aliases("retired", "metadata_key"))
#: The surviving bag, which keeps its name and is free to be written down.
SURVIVING_COLUMN = "metadata"


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name for column in
                connection.introspection.get_table_description(
                    cursor, Posting._meta.db_table)}


class TheSecondBagIsGoneTest(TestCase):
    def test_the_model_declares_no_such_field(self):
        assert RETIRED_COLUMN not in {f.name for f in Posting._meta.get_fields()}

    def test_the_table_carries_no_such_column(self):
        """The model and the table are two separate claims.

        A field absent from the model while the schema still carries it leaves
        the column in the database, where a raw query would still find it.
        """
        assert RETIRED_COLUMN not in _live_columns()

    def test_the_surviving_bag_is_still_there(self):
        """A fold that dropped both bags would pass every absence test above."""
        assert SURVIVING_COLUMN in _live_columns()

    def test_the_surviving_bag_carries_the_filtering_index(self):
        """FILTERING IS WHAT SURVIVES THE FOLD, and filtering a JSON bag
        without a GIN index is a sequential scan of the largest table in the
        system. The retired bag carried one (usage/0022, before the cutover)
        for exactly the containment and key-exists lookups that now run
        against this one.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s "
                "AND indexname = %s",
                [Posting._meta.db_table, "idx_posting_metadata"])
            row = cursor.fetchone()
        assert row is not None, "the surviving bag has no GIN index"
        assert "gin" in row[0].lower()
        # Default `jsonb_ops`, not `jsonb_path_ops`: only the default opclass
        # serves the key-exists operator `__has_key` compiles to.
        assert "jsonb_path_ops" not in row[0]


class TheBagIsNotAGroupingAxisTest(TestCase):
    """FILTERABLE AND READABLE, NEVER GROUPABLE — on every surface since slice 7.

    **This claim used to carry a limit, and the limit is the history worth
    keeping.** What slice 2 could pin was that the surviving bag, BY ITS OWN
    NAME, is not a grouping axis anywhere: it is not a groupable column, and
    naming it as an invoice-line grouping does not read it. Three surfaces
    still read keys OUT of it then — the keyed analytics parameter, the keyed
    margin breakdown and the key-driven invoice line labels — so an unbounded
    key could still reach a chart and an invoice line, and slice 2 named slice
    7 as where that capability moves onto the declared grouping contract.

    ⚠ **IT MOVED, AND ALL THREE READERS ARE GONE.** The one economic query
    (#499) groups by declared axes and by nothing else and takes no parameter
    that can name a key in here; the keyed parameter and the keyed margin
    breakdown died with their routes (#501); and an invoice line's grouping is
    one declared axis (#503), so a `tag:` value is a word naming no grouping
    kind and is refused. The cases below say so one surface at a time.

    What made the three worth naming was that the fold WIDENED what they read:
    the retired bag was validated flat `str -> str` on the recording path and
    the survivor never was, so a label could arrive as a serialised object
    rather than a short string. It closed by there being no key left to hand —
    `test_a_nested_value_can_no_longer_reach_the_label_path` keeps the fixture
    that used to get through. The alternative, imposing the retired bag's
    value rules on a published field that never had them, was a break slice 2
    was not asked to make — the module note in `services/usage_service.py`
    takes all four rules one at a time.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()

    def test_the_bag_is_not_a_groupable_column(self):
        """The one economic query's axes are the ones the discovery contract
        publishes, and the open bag is not one of them — nor is any key inside
        it, which is the whole difference between a declared axis and a bag.

        ⚠ IT ASKED THE GROUPED MARGIN UNTIL #501 DELETED IT, and the claim moved
        to the query that replaced it rather than dying with the surface: the
        axis word carries its own kind now, so the bag's name is refused twice
        over — as a kind nobody declared, and as a field nobody declared.
        """
        from apps.metering.queries import economics, grouping_axis
        from core.vocabulary import (
            ANALYTICS_GROUPING_KIND_FIELD, ANALYTICS_MEASURE_SUPPLIER_COGS)
        for named in (SURVIVING_COLUMN, f"{SURVIVING_COLUMN}__department"):
            with self.subTest(group_by=named):
                with self.assertRaises(ValueError):
                    economics(self.tenant.id,
                              measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                              group_by=[grouping_axis(
                                  ANALYTICS_GROUPING_KIND_FIELD, named)])

    def test_the_bag_is_not_a_declarable_grouping_field_target(self):
        """A declared Grouping Field binds a tenant key to a physical SLOT.
        There is no slot that is the bag, so no declaration can point at it.
        """
        from apps.platform.grouping_fields.models import SLOT_CHOICES
        assert SURVIVING_COLUMN not in dict(SLOT_CHOICES)

    def test_naming_the_bag_as_an_invoice_line_grouping_is_refused(self):
        """THE SILENT FALL-THROUGH THIS TEST RECORDED IS CLOSED (#503, §11).

        It used to say: *the reader recognises the `tag:` prefix and otherwise
        falls through to `dim1`, so an unrecognised grouping is silently grouped
        by a column the caller did not name* — and that *the silent fallback
        underneath is a defect in a slice-7-owned surface, recorded here rather
        than repaired here.* This is the repair. The bag is still not read, and
        it is no longer read as something else either: a word the discovery
        contract does not publish is refused.
        """
        from apps.metering.queries import get_customer_billed_breakdown
        from datetime import date
        a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i_lbl",
            billed_cost_micros=500_000, grouping_field_1="chat",
            metadata={"seat": "alice"})

        # The MESSAGE, not just the type: `_axis_plan` raises its own
        # `ValueError` further in, so a bare type check would pass over the read
        # contract falling over rather than refusing.
        with self.assertRaisesRegex(ValueError, "names no grouping kind"):
            get_customer_billed_breakdown(
                self.tenant.id, self.customer.id, date(2020, 1, 1),
                date(2100, 1, 1), group_by=SURVIVING_COLUMN)

    def test_a_nested_value_can_no_longer_reach_the_label_path(self):
        """THE WIDENING THE FOLD OPENED, CLOSED (#503, slice 7 §11).

        This test used to RUN the widening rather than assert it away: the
        retiring bag was validated flat `str -> str` on the recording path, the
        survivor never was, and a key-driven invoice line label could therefore
        be handed a serialised object where it used to be handed a short string.
        Nothing was ever mis-metered by it and no money moved — the label was
        ugly and unbounded, on the one surface a paying customer reads.

        It said *this is the widening slice 7 closes when it moves grouping onto
        the declared contract, pinned here so that closing it is a change to a
        red test rather than a discovery.* It is closed by there being no key to
        hand: an invoice line's axis is one the tenant declared, and a
        declaration binds a key to a SLOT, which the test above shows the bag
        can never be.

        ⚠ **THE REFUSAL IS THE SAME ONE ITS SIBLING ABOVE GETS, AND THAT IS THE
        RESULT RATHER THAN A WEAKNESS IN THE TEST.** The bag used to have a
        reader of its own on this surface — a `tag:` prefix the label path
        recognised — and what closed the widening is that the prefix is now
        just a word naming no kind, handled by the same sentence as any other.
        The nested value is kept as the fixture because it is the thing that
        used to get through; it can no longer get as far as being serialised.
        """
        from apps.metering.queries import get_customer_billed_breakdown
        from datetime import date
        a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i_nested",
            billed_cost_micros=500_000,
            metadata={"request": {"model": "gpt-5", "stream": True}})

        with self.assertRaisesRegex(ValueError, "names no grouping kind") as raised:
            get_customer_billed_breakdown(
                self.tenant.id, self.customer.id, date(2020, 1, 1),
                date(2100, 1, 1), group_by="tag:request")
        # Nothing of the bag reached the message: a refusal that echoed the
        # serialised object back would be the same unbounded string arriving one
        # surface further along.
        assert "gpt-5" not in str(raised.exception)
