"""Markup resolution — the last rung of the price ladder.

Precedence (design doc §5):

    customer TenantMarkup override -> customer's Plan -> tenant default -> none

The plan rung is why a Personal Lite customer (50%) cannot silently bill at
the tenant default (20%). Plans live in the kernel, so reading them here is
an apps.platform.* import, not a cross-product one (ADR-001 rule 1).

**A RUNG ANSWERS A PERCENTAGE AND ITS SOURCE, NEVER A FINISHED NUMBER (#356).**
This module used to expose an applier that took a supplier cost and handed back
the marked-up figure, and the receipt writer at the other end of it could only
record that markup had happened — not which rung supplied it, nor which record
the percentage came from. Those are exactly what a tenant asked *"why is this
line £36?"* has to be shown, and they cannot be reconstructed afterwards,
because a markup record can be edited. So the resolver takes the resolved value
and applies it itself, with the source still in its hand at the point the record
is built.

**AND A COST UBB HAS NOT RESOLVED NO LONGER REACHES HERE AT ALL.** The applier
carried a refusal for it (#328) because a markup is not a total: there is no
"at least" to state about a single price, so the honest answers were a real
basis or an error. The resolver now asks the question one step earlier and in
the vocabulary the answer belongs in — a margin over a cost UBB never learned is
a `waived` charge — so the case is decided before a percentage is even resolved,
and the refusal has no caller left to protect.
"""
from dataclasses import dataclass

from apps.metering.pricing.models import TenantMarkup


@dataclass(frozen=True)
class ResolvedMarkup:
    """The markup that applies to one (tenant, customer), and where it came from.

    Frozen: instances are shared through the L1 cache and must never be mutated
    by a caller. ``source`` is carried for provenance — it answers "why was this
    event priced this way" without re-deriving the chain.
    """
    markup_percentage_micros: int
    fixed_uplift_micros: int
    source: str  # "customer" | "plan" | "tenant_default"

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        # Rounding is half-up on the micro, matching TenantMarkup exactly —
        # changing it would silently re-price every event.
        percent = (
            provider_cost_micros * self.markup_percentage_micros + 50_000_000
        ) // 100_000_000
        return percent + self.fixed_uplift_micros

    def applied_to(self, provider_cost_micros: int) -> int:
        """The customer price this rung answers over a basis it is given.

        The basis plus the markup taken on it, said once. It is a method rather
        than two lines at the resolver because the cache's whole contract is
        that it answers what a live resolve answers, and a sum written at each
        caller is how two callers come to disagree about what "marked up" meant.

        The caller decides whether a basis may be marked up at all: an
        `unresolved` cost is `waived` and never arrives here, and a resolved
        zero IS a basis — a call that genuinely cost nothing, marked up to the
        uplift.
        """
        return provider_cost_micros + self.calculate_markup_micros(
            provider_cost_micros)


def _from_tenant_markup(row, source):
    return ResolvedMarkup(
        markup_percentage_micros=row.markup_percentage_micros,
        fixed_uplift_micros=row.fixed_uplift_micros,
        source=source,
    )


class MarkupService:
    @staticmethod
    def resolve(tenant, customer):
        """Return the applicable ResolvedMarkup, or None if nothing applies."""
        if customer is not None:
            override = TenantMarkup.objects.filter(
                tenant=tenant, customer=customer).first()
            if override:
                return _from_tenant_markup(override, "customer")

            from apps.platform.plans.queries import get_plan_markup_for_customer
            plan_markup = get_plan_markup_for_customer(tenant.id, customer.id)
            if plan_markup is not None:
                return ResolvedMarkup(source="plan", **plan_markup)

        default = TenantMarkup.objects.filter(
            tenant=tenant, customer__isnull=True).first()
        if default:
            return _from_tenant_markup(default, "tenant_default")
        return None
