"""Markup resolution.

Precedence (design doc §5):

    customer TenantMarkup override -> customer's Plan -> tenant default -> none

The plan rung is why a Personal Lite customer (50%) cannot silently bill at
the tenant default (20%). Plans live in the kernel, so reading them here is
an apps.platform.* import, not a cross-product one (ADR-001 rule 1).
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

    @staticmethod
    def apply(provider_cost_micros, tenant, customer):
        """billed = provider + markup(provider); nothing configured -> billed == provider."""
        markup = MarkupService.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
