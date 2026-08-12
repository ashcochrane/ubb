"""Tests backing ADR-0005, in the manner ADR-001 establishes: the hard rules
are enforced here, not merely documented.

EVERY REFUSAL BELOW IS DRIVEN AT EVERY SLOT, not at a representative one. #276
took the count from six to ten and re-spelled all of them, and the failure it
made possible is a rule that holds on the slots that already existed and lapses
on the ones that did not — which a single hard-coded slot would never find. The
loops are over the declared vocabulary rather than a literal ten, so a later
widening is covered by construction rather than by someone remembering.
"""
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import SLOT_CHOICES, GroupingField
from apps.platform.grouping_fields.services import DimensionError, DimensionService

SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)


@pytest.mark.django_db
class TestGroupingFieldInvariants:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_slot_rebinding_is_refused(self):
        for origin, destination in zip(SLOTS, SLOTS[1:] + SLOTS[:1]):
            t = self._t()
            DimensionService.declare(t, key="region", slot=origin, scope="task")
            with pytest.raises(DimensionError, match="immutable"):
                DimensionService.declare(t, key="region", slot=destination, scope="task")

    def test_scope_change_is_refused(self):
        for slot in SLOTS:
            t = self._t()
            DimensionService.declare(t, key="region", slot=slot, scope="task")
            with pytest.raises(DimensionError, match="immutable"):
                DimensionService.declare(t, key="region", slot=slot, scope="event")

    def test_cardinality_cannot_be_lowered(self):
        for slot in SLOTS:
            t = self._t()
            DimensionService.declare(t, key="region", slot=slot, scope="task",
                                     max_cardinality=100)
            with pytest.raises(DimensionError, match="lowered"):
                DimensionService.declare(t, key="region", slot=slot, scope="task",
                                         max_cardinality=99)

    def test_every_correlation_id_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.grouping_fields.models import FORBIDDEN_KEYS
        for key in FORBIDDEN_KEYS:
            for slot in SLOTS:
                with pytest.raises(DimensionError, match="correlation"):
                    DimensionService.declare(t, key=key, slot=slot, scope="event")

    def test_every_reserved_key_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.grouping_fields.models import RESERVED_KEYS
        for key in RESERVED_KEYS:
            for slot in SLOTS:
                with pytest.raises(DimensionError, match="reserved"):
                    DimensionService.declare(t, key=key, slot=slot, scope="event")

    def test_a_slot_outside_the_vocabulary_is_refused(self):
        """#276's own refusal, and it exists because the alternative is silent.

        A stored slot IS a column name: `admit` returns `{slot: value}` and the
        recording path copies across only the slots it knows about. A
        declaration bound to a slot that does not exist therefore stores fine,
        accepts values fine, returns 200 fine — and attributes every one of them
        to nothing. The tenant finds out when a chart is missing a column.

        The case that makes this concrete is a caller written against the six
        slots this ticket replaced, which is why the retired spelling is one of
        the three driven here.
        """
        t = self._t()
        for slot in ("dim1", "slot_1", ""):
            with pytest.raises(DimensionError, match="is not a slot"):
                DimensionService.declare(t, key="region", slot=slot, scope="event")

    def test_every_declared_slot_is_accepted(self):
        """The control for the refusal above.

        Without it, a typo in the vocabulary check would refuse everything and
        every other test in this class would still pass — they all assert
        refusals.
        """
        t = self._t()
        for position, slot in enumerate(SLOTS):
            declared = DimensionService.declare(
                t, key=f"key_{position}", slot=slot, scope="event")
            assert declared.slot == slot

    def test_retired_def_stays_in_the_slot_map(self):
        """Retirement blocks new VALUES, not reads — historical rows must stay
        groupable (design D8)."""
        from django.utils import timezone
        from apps.platform.grouping_fields.queries import slot_map
        t = self._t()
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task")
        GroupingField.objects.filter(tenant=t, key="region").update(
            retired_at=timezone.now())
        assert slot_map(t.id)["region"] == "grouping_field_1"

    def test_posting_and_rate_share_one_selector_vocabulary(self):
        """The unification (design D3): one word list, both sides.

        **Re-pointed at the Posting by #269, not retired with the old noun.**
        ADR-0005's design was declared superseded, but the agreement this pins
        is still live: `Rate.SELECTORS` and the specificity ranking built on it
        both survive to **slice 4**, which is where the rate entity, the rate
        book and the selector list are rebuilt. Until then a rate resolves
        against columns on this table, and a slice that renamed the vocabulary
        underneath the test while deleting the test would have removed the only
        thing checking the two lists still agree.

        **Dissolving the agreement is slice 4's business**, and deleting this
        test belongs to whoever does it — with the replacement in the same
        change, not before it.
        """
        from apps.metering.pricing.models import Rate
        from apps.metering.usage.models import Posting
        posting_cols = {f.name for f in Posting._meta.get_fields()}
        for selector in Rate.SELECTORS:
            assert selector in posting_cols, (
                f"Rate selects on {selector!r} but Posting has no such column")

    def test_book_tier_dominates_rate_specificity(self):
        """The composite ranking rule (surfaced late in review, documented in
        ADR-0005): `_resolve_card` walks book tiers — assigned book, then the
        provider-specific default book, then the provider-agnostic ("") default
        book — and returns as soon as a TIER yields any match at all. "Most
        pinned wins" only holds WITHIN one book.

        Here the "" book carries a narrowly-pinned override (task_type + dim1,
        specificity 2) while the provider-specific "openai" book carries only a
        broad provider pin (specificity 1). Naive "most selectors wins" ranking
        across the whole rate set would pick the "" book's rate. The real
        resolution never gets that far: the openai book is tried first, finds a
        match, and returns immediately — the "" book's more specific override
        is silently shadowed."""
        from apps.metering.pricing.services.pricing_service import PricingService
        from apps.metering.pricing.tests._helpers import rate_in_default_book

        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="cust-1")

        # "" (provider-agnostic) default book: narrow, highly-pinned override.
        rate_in_default_book(
            t, card_type="cost", provider="", task_type="invoice_batch",
            grouping_field_1="eu-west-1", measurement_key="input_tokens",
            rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        # "openai" provider-specific default book: broad, single-selector rate.
        rate_in_default_book(
            t, card_type="cost", provider="openai", measurement_key="input_tokens",
            rate_per_unit_micros=9_000, unit_quantity=1_000_000)

        selectors = {"provider": "openai", "event_type": "", "task_type": "invoice_batch",
                    "subtask_type": "",
                     "grouping_field_1": "eu-west-1",
                     "grouping_field_2": "", "grouping_field_3": "", "grouping_field_4": "", "grouping_field_5": "", "grouping_field_6": "", "grouping_field_7": "", "grouping_field_8": "", "grouping_field_9": "", "grouping_field_10": ""}
        provider_cost, _, provenance = PricingService.price(
            tenant=t, customer=c, selectors=selectors,
            measurements={"input_tokens": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)

        # The openai book's broad, specificity-1 rate wins over the ""
        # book's narrow, specificity-2 override — book tier beats specificity.
        assert provider_cost == 9_000
        assert provenance["cost_source"] == "rate_card"
