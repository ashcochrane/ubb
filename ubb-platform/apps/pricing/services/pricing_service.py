"""Pricing service: rate lookup, dimension matching, markup application."""

import logging
from typing import Dict, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from apps.pricing.models import ProviderRate, TenantMarkup

logger = logging.getLogger(__name__)

PRICING_ENGINE_VERSION = "1.0.0"


class PricingError(Exception):
    pass


class PricingService:
    """
    Calculates dual costs (provider COGS + billed revenue) from raw usage metrics.

    Pipeline per metric:
      1. Find matching ProviderRate (dimension match, most-specific wins)
      2. calculate_cost_micros(units) -> provider_cost_micros

    Then for the event total:
      3. Find TenantMarkup (event_type+provider -> event_type -> global)
      4. Apply markup -> billed_cost_micros
    """

    @staticmethod
    def validate_usage_metrics(usage_metrics: Dict) -> None:
        """Validate that all metric values are non-negative integers."""
        for key, value in usage_metrics.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise PricingError(
                    f"Metric '{key}' must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise PricingError(
                    f"Metric '{key}' must be >= 0, got {value}"
                )

    @staticmethod
    def price_event(
        tenant,
        event_type: str,
        provider: str,
        usage_metrics: Dict[str, int],
        properties: Dict = None,
        as_of=None,
    ) -> Tuple[int, int, Dict]:
        """
        Price a usage event from raw metrics.

        Args:
            tenant: Tenant instance
            event_type: e.g. "gemini_api_call"
            provider: e.g. "google_gemini"
            usage_metrics: e.g. {"input_tokens": 1500, "output_tokens": 300}
            properties: dimension values for rate matching, e.g. {"model": "gemini-2.0-flash"}
            as_of: pricing effective timestamp (default: now)

        Returns:
            (provider_cost_micros, billed_cost_micros, provenance)

        Raises:
            PricingError: if no rate found for a metric, or invalid metric values
        """
        as_of = as_of or timezone.now()
        properties = properties or {}

        if not usage_metrics:
            return 0, 0, {"engine_version": PRICING_ENGINE_VERSION, "metrics": {}}

        PricingService.validate_usage_metrics(usage_metrics)

        total_provider_cost = 0
        provenance_metrics = {}

        for metric_name, units in usage_metrics.items():
            rate = PricingService._find_rate(
                provider=provider,
                event_type=event_type,
                metric_name=metric_name,
                properties=properties,
                as_of=as_of,
            )
            if rate is None:
                raise PricingError(
                    f"No rate found: {provider}/{event_type}/{metric_name} "
                    f"properties={properties}"
                )

            metric_cost = rate.calculate_cost_micros(units)
            total_provider_cost += metric_cost

            provenance_metrics[metric_name] = {
                "rate_id": str(rate.id),
                "units": units,
                "cost_per_unit_micros": rate.cost_per_unit_micros,
                "unit_quantity": rate.unit_quantity,
                "dimensions": rate.dimensions,
                "cost_micros": metric_cost,
            }

        # Apply tenant markup
        markup_obj = PricingService._find_markup(
            tenant=tenant,
            event_type=event_type,
            provider=provider,
            as_of=as_of,
        )

        markup_micros = 0
        markup_provenance = {}
        if markup_obj:
            markup_micros = markup_obj.calculate_markup_micros(total_provider_cost)
            markup_provenance = {
                "markup_id": str(markup_obj.id),
                "percentage_micros": markup_obj.markup_percentage_micros,
                "fixed_uplift_micros": markup_obj.fixed_uplift_micros,
                "markup_micros": markup_micros,
            }

        billed_cost = total_provider_cost + markup_micros

        provenance = {
            "engine_version": PRICING_ENGINE_VERSION,
            "calculated_at": as_of.isoformat(),
            "metrics": provenance_metrics,
            "markup": markup_provenance,
            "provider_cost_micros": total_provider_cost,
            "billed_cost_micros": billed_cost,
        }

        return total_provider_cost, billed_cost, provenance

    @staticmethod
    def _find_rate(
        provider: str,
        event_type: str,
        metric_name: str,
        properties: Dict,
        as_of,
    ) -> Optional[ProviderRate]:
        """Find best matching ProviderRate using dimension matching."""
        rates = ProviderRate.objects.filter(
            provider=provider,
            event_type=event_type,
            metric_name=metric_name,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))

        matched = []
        for rate in rates:
            if PricingService._dimensions_match(rate.dimensions, properties):
                matched.append(rate)

        if not matched:
            return None

        # Most specific (most dimension keys), then newest valid_from
        matched.sort(
            key=lambda r: (len(r.dimensions) if r.dimensions else 0, r.valid_from),
            reverse=True,
        )
        return matched[0]

    @staticmethod
    def _dimensions_match(rate_dimensions: Dict, event_properties: Dict) -> bool:
        """All rate dimension key-values must exist in event properties."""
        if not rate_dimensions:
            return True
        return all(
            event_properties.get(k) == v for k, v in rate_dimensions.items()
        )

    @staticmethod
    def _find_markup(tenant, event_type: str, provider: str, as_of) -> Optional[TenantMarkup]:
        """
        Find best TenantMarkup with precedence:
          1. tenant + event_type + provider
          2. tenant + event_type
          3. tenant (global)
        """
        base = TenantMarkup.objects.filter(
            tenant=tenant,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))

        # Most specific first
        markup = base.filter(event_type=event_type, provider=provider).order_by("-valid_from").first()
        if markup:
            return markup

        markup = base.filter(event_type=event_type, provider="").order_by("-valid_from").first()
        if markup:
            return markup

        markup = base.filter(event_type="", provider="").order_by("-valid_from").first()
        return markup
