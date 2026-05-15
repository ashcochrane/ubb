"""Explicit-rate pricing service. No runtime margin resolution.

Each Rate carries provider_cost_per_unit_micros (what the provider charges) and
cost_per_unit_micros (what the tenant charges its customer). Pricing is a simple
lookup-and-sum; there is no cascade and no TenantMarkup.
"""

import logging
from typing import Dict, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Card, Rate

logger = logging.getLogger(__name__)

PRICING_ENGINE_VERSION = "3.0.0"


class PricingError(Exception):
    pass


class PricingService:
    """Calculate dual costs (provider + billed) from stored Rates. No margin math."""

    @staticmethod
    def validate_usage_metrics(usage_metrics: Dict) -> None:
        for key, value in usage_metrics.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise PricingError(
                    f"Metric '{key}' must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise PricingError(f"Metric '{key}' must be >= 0, got {value}")

    @staticmethod
    def price_event_by_slug(
        tenant,
        card_slug: str,
        usage_metrics: Dict[str, int],
        group: str = None,  # accepted but unused; kept for caller compatibility
        as_of=None,
    ) -> Tuple[int, int, Dict, Optional[Card]]:
        """Price an event using direct card slug lookup.

        Returns (provider_cost_micros, billed_cost_micros, provenance, card).
        """
        as_of = as_of or timezone.now()

        if not usage_metrics:
            return 0, 0, {"engine_version": PRICING_ENGINE_VERSION, "metrics": {}}, None

        PricingService.validate_usage_metrics(usage_metrics)

        try:
            card = Card.objects.get(
                tenant=tenant, slug=card_slug, status="active",
            )
        except Card.DoesNotExist:
            raise PricingError(
                f"No active pricing card found with slug '{card_slug}'"
            )

        total_provider_cost = 0
        total_billed_cost = 0
        provenance_metrics = {}

        for metric_name, units in usage_metrics.items():
            rate = PricingService._find_rate(card, metric_name, as_of)
            if rate is None:
                raise PricingError(
                    f"No rate found for metric '{metric_name}' in card '{card.name}'"
                )
            billed_for_metric = rate.calculate_cost_micros(units)
            provider_unit = (
                rate.provider_cost_per_unit_micros
                if rate.provider_cost_per_unit_micros is not None
                else rate.cost_per_unit_micros
            )
            provider_for_metric = PricingService._cost(
                units, provider_unit, rate.unit_quantity, rate.pricing_type,
            )

            total_provider_cost += provider_for_metric
            total_billed_cost += billed_for_metric

            provenance_metrics[metric_name] = {
                "rate_id": str(rate.id),
                "units": units,
                "pricing_type": rate.pricing_type,
                "cost_per_unit_micros": rate.cost_per_unit_micros,
                "provider_cost_per_unit_micros": rate.provider_cost_per_unit_micros,
                "unit_quantity": rate.unit_quantity,
                "billed_cost_micros": billed_for_metric,
                "provider_cost_micros": provider_for_metric,
            }

        provenance = {
            "engine_version": PRICING_ENGINE_VERSION,
            "calculated_at": as_of.isoformat(),
            "card_id": str(card.id),
            "card_slug": card.slug,
            "card_name": card.name,
            "metrics": provenance_metrics,
            "provider_cost_micros": total_provider_cost,
            "billed_cost_micros": total_billed_cost,
        }

        return total_provider_cost, total_billed_cost, provenance, card

    @staticmethod
    def _cost(units: int, per_unit: int, unit_quantity: int, pricing_type: str) -> int:
        if pricing_type == "flat":
            return per_unit
        return (units * per_unit + unit_quantity // 2) // unit_quantity

    @staticmethod
    def _find_rate(card: Card, metric_name: str, as_of) -> Optional[Rate]:
        return card.rates.filter(
            metric_name=metric_name,
            valid_from__lte=as_of,
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)
        ).order_by("-valid_from").first()
