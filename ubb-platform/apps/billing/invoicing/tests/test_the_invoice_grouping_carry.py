"""Migration `0009` carries every stored invoice-line grouping onto an axis (#503).

⚠ **A RENAME THAT CARRIES EVERY ROW AND LEAVES THEM ALL SAYING A WORD THAT NO
LONGER MEANS ANYTHING IS NOT A FAILED MIGRATION — IT IS A WRONG INVOICE.** The
column's operation list is ADR-0007 §1's subject and `makemigrations --check`
covers it; what these cases are about is what the column HOLDS afterwards. A
tenant left holding `tag:region` would have their next invoice refused by the
read contract, and one left holding a word that happens to parse would be billed
under headings they never chose.

**The two readings the old column had are two different facts, and each is
carried to what it ACTUALLY DID** — not to what it looked like:

* a `tag:` value read the free-form bag, which #273 closed for grouping, so
  there is no axis to carry it to unless the tenant has since declared a field
  of that name;
* **anything else meant the first slot**, whatever it spelled, which is the
  silent fall-through `test_the_second_open_bag_folds.py` recorded as slice 7's
  to repair.

Driven through the migration's own function over the live table, on
`test_the_rates_arithmetic_shape_takes_its_ratified_name.py`'s precedent: what
is exercised is the code that will run rather than a restatement of it. The
model still exists at HEAD — the migration renames a column rather than deleting
its source — so the live models are the right stand-in, unlike #496's carry.
"""
import importlib

from django.test import TestCase

from apps.billing.invoicing.models import PostpaidUsageConfig
from apps.metering.queries import grouping_axis
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant
from core.vocabulary import ANALYTICS_GROUPING_KIND_FIELD

MIGRATION = importlib.import_module(
    "apps.billing.invoicing.migrations."
    "0009_invoice_lines_take_the_one_grouping_vocabulary")


class _LiveApps:
    """`apps.get_model`'s interface, answered with the live models.

    Narrow on purpose — it answers for the two models the carry reads and
    nothing else, so a carry that started reaching for a third fails here
    loudly instead of being handed a registry that quietly serves it.
    """

    def get_model(self, app_label, model_name):
        return {("invoicing", "PostpaidUsageConfig"): PostpaidUsageConfig,
                ("grouping_fields", "GroupingField"): GroupingField,
                }[(app_label, model_name)]


class TheFrozenSpellingsAreTheLivingOnesTest(TestCase):
    """A migration may not follow a constant that later moves, so it spells the
    axis words as literals — and the literals are held to the living spelling
    here rather than trusted.

    This is the test that goes red the day the request vocabulary changes shape,
    which is the only way a frozen snapshot can be kept honest.
    """

    def test_the_frozen_field_prefix_is_what_the_read_contract_builds(self):
        assert (MIGRATION.FIELD_AXIS + "region"
                == grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "region"))

    def test_the_frozen_first_slot_is_a_slot_the_registry_declares(self):
        from apps.platform.grouping_fields.models import SLOTS
        assert MIGRATION.FIRST_SLOT == SLOTS[0]


class TheCarryReadsWhatEachValueDidTest(TestCase):
    """Each stored shape, carried to the axis it was really grouping by."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="T", billing_mode="postpaid",
            products=["metering", "billing"])
        self.apps = _LiveApps()

    def _stored(self, value):
        config = PostpaidUsageConfig.objects.create(
            tenant=self.tenant, invoice_line_grouping=value)
        MIGRATION._carry_onto_the_one_vocabulary(self.apps, None)
        config.refresh_from_db()
        return config.invoice_line_grouping

    def test_no_grouping_stays_no_grouping(self):
        assert self._stored("") == ""

    def test_a_bag_key_the_tenant_has_since_declared_becomes_that_axis(self):
        """The one case where the tenant's intent survives intact: they were
        labelling by a key they have since made a real axis."""
        DimensionService.declare(self.tenant, key="region",
                                 slot="grouping_field_2", scope="event")
        assert self._stored("tag:region") == "field:region"

    def test_a_bag_key_with_no_declaration_behind_it_is_cleared(self):
        """⚠ **CLEARED RATHER THAN GUESSED**, and the direction matters. The bag
        is not a grouping axis and has not been since #273, so there is nothing
        to carry this to. One line per period is a legible invoice the tenant
        can re-group deliberately; a heading UBB invented for them is not.
        """
        assert self._stored("tag:nothing_declared") == ""

    def test_anything_else_becomes_the_axis_the_first_slot_really_was(self):
        """The silent fall-through, carried to what it DID rather than to what
        it said. `product_id` never meant a field called `product_id` — it meant
        `grouping_field_1`, whatever the tenant had bound to it."""
        DimensionService.declare(self.tenant, key="region",
                                 slot="grouping_field_1", scope="event")
        assert self._stored("product_id") == "field:region"

    def test_anything_else_with_nothing_bound_to_the_first_slot_is_cleared(self):
        """A column with no declaration behind it is not an axis: the registry
        is what makes a slot groupable, which is ADR-0005's whole rule."""
        assert self._stored("product_id") == ""

    def test_a_value_that_already_names_an_axis_is_not_double_prefixed(self):
        """⚠ **THE CARRY MUST BE SAFE TO MEET A NEW-STYLE VALUE**, because
        nothing stops one being written before the migration runs on a developer
        machine — and `field:field:region` would parse as an axis named
        `field:region`, which is a refusal a reader could not explain.

        It reaches the first slot, which is what the pre-#503 reader would have
        done with it, and lands on the axis bound there.
        """
        DimensionService.declare(self.tenant, key="region",
                                 slot="grouping_field_1", scope="event")
        assert self._stored("field:region") == "field:region"

    def test_one_tenants_declaration_does_not_carry_anothers_config(self):
        """The carry is per tenant, which a `GroupingField` lookup that forgot
        to filter would silently break — and it would break it in the worst
        direction, by finding SOMEBODY's axis and billing against it."""
        other = Tenant.objects.create(name="Other", billing_mode="postpaid",
                                      products=["metering", "billing"])
        DimensionService.declare(other, key="region", slot="grouping_field_1",
                                 scope="event")
        assert self._stored("tag:region") == ""
