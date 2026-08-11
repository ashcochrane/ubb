"""Tests backing ADR-0005, in the manner ADR-001 establishes: the hard rules
are enforced here, not merely documented."""
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.grouping_fields.services import DimensionError, DimensionService


@pytest.mark.django_db
class TestGroupingFieldInvariants:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_slot_rebinding_is_refused(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="immutable"):
            DimensionService.declare(t, key="region", slot="dim4", scope="task")

    def test_scope_change_is_refused(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        with pytest.raises(DimensionError, match="immutable"):
            DimensionService.declare(t, key="region", slot="dim1", scope="event")

    def test_cardinality_cannot_be_lowered(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                 max_cardinality=100)
        with pytest.raises(DimensionError, match="lowered"):
            DimensionService.declare(t, key="region", slot="dim1", scope="task",
                                     max_cardinality=99)

    def test_every_correlation_id_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.grouping_fields.models import FORBIDDEN_KEYS
        for key in FORBIDDEN_KEYS:
            with pytest.raises(DimensionError, match="correlation"):
                DimensionService.declare(t, key=key, slot="dim1", scope="event")

    def test_every_reserved_key_is_refused_as_a_dimension(self):
        t = self._t()
        from apps.platform.grouping_fields.models import RESERVED_KEYS
        for key in RESERVED_KEYS:
            with pytest.raises(DimensionError, match="reserved"):
                DimensionService.declare(t, key=key, slot="dim1", scope="event")

    def test_retired_def_stays_in_the_slot_map(self):
        """Retirement blocks new VALUES, not reads — historical rows must stay
        groupable (design D8)."""
        from django.utils import timezone
        from apps.platform.grouping_fields.queries import slot_map
        t = self._t()
        DimensionService.declare(t, key="region", slot="dim1", scope="task")
        GroupingField.objects.filter(tenant=t, key="region").update(
            retired_at=timezone.now())
        assert slot_map(t.id)["region"] == "dim1"

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
            dim1="eu-west-1", metric_name="input_tokens",
            rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        # "openai" provider-specific default book: broad, single-selector rate.
        rate_in_default_book(
            t, card_type="cost", provider="openai", metric_name="input_tokens",
            rate_per_unit_micros=9_000, unit_quantity=1_000_000)

        selectors = {"provider": "openai", "event_type": "", "task_type": "invoice_batch",
                    "subtask_type": "", "dim1": "eu-west-1", "dim2": "", "dim3": "",
                    "dim4": "", "dim5": "", "dim6": ""}
        provider_cost, _, provenance = PricingService.price(
            tenant=t, customer=c, selectors=selectors,
            measurements={"input_tokens": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)

        # The openai book's broad, specificity-1 rate wins over the ""
        # book's narrow, specificity-2 override — book tier beats specificity.
        assert provider_cost == 9_000
        assert provenance["cost_source"] == "rate_card"
