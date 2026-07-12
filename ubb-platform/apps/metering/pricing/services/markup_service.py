from apps.metering.pricing.models import TenantMarkup


class MarkupService:
    @staticmethod
    def resolve(tenant, customer):
        """Return the applicable TenantMarkup (customer override → tenant default → None)."""
        if customer is not None:
            m = TenantMarkup.objects.filter(tenant=tenant, customer=customer).first()
            if m:
                return m
        return TenantMarkup.objects.filter(tenant=tenant, customer__isnull=True).first()

    @staticmethod
    def apply(provider_cost_micros, tenant, customer):
        """billed = provider + markup(provider); no markup configured → billed == provider."""
        markup = MarkupService.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
