"""Pricing service: Card/Rate lookup, dimension matching, margin resolution."""

import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Card, Rate, TenantMarkup

logger = logging.getLogger(__name__)

PRICING_ENGINE_VERSION = "2.0.0"


class PricingError(Exception):
    pass


class PricingService:
    """
    Calculates dual costs (provider COGS + billed revenue) from raw usage metrics.

    Pipeline:
      1. Find matching Card (dimension match, most-specific wins)
      2. For each metric: find Rate in Card, calculate cost
      3. Resolve margin: card-level TenantMarkup -> Group -> parent chain -> default TenantMarkup
      4. Apply margin -> billed_cost_micros
    """

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
    def price_event(
        tenant,
        event_type: str,
        provider: str,
        usage_metrics: Dict[str, int],
        properties: Dict = None,
        group: str = None,
        as_of=None,
    ) -> Tuple[int, int, Dict]:
        as_of = as_of or timezone.now()
        properties = properties or {}

        if not usage_metrics:
            return 0, 0, {"engine_version": PRICING_ENGINE_VERSION, "metrics": {}}

        PricingService.validate_usage_metrics(usage_metrics)

        # Find the matching Card
        card = PricingService._find_card(tenant, provider, event_type, properties, as_of)
        if card is None:
            raise PricingError(
                f"No pricing card found: {provider}/{event_type} "
                f"properties={properties}"
            )

        # Calculate provider cost from Card's Rates
        total_provider_cost = 0
        provenance_metrics = {}

        for metric_name, units in usage_metrics.items():
            rate = PricingService._find_rate(card, metric_name, as_of)
            if rate is None:
                raise PricingError(
                    f"No rate found for metric '{metric_name}' in card '{card.name}'"
                )
            metric_cost = rate.calculate_cost_micros(units)
            total_provider_cost += metric_cost

            provenance_metrics[metric_name] = {
                "rate_id": str(rate.id),
                "card_id": str(card.id),
                "units": units,
                "cost_per_unit_micros": rate.cost_per_unit_micros,
                "unit_quantity": rate.unit_quantity,
                "cost_micros": metric_cost,
            }

        # Resolve and apply margin
        margin_pct, margin_source = PricingService._resolve_margin(
            tenant, event_type, provider, group, as_of,
        )
        billed_cost = PricingService._apply_margin(total_provider_cost, margin_pct)

        provenance = {
            "engine_version": PRICING_ENGINE_VERSION,
            "calculated_at": as_of.isoformat(),
            "card_id": str(card.id),
            "card_name": card.name,
            "metrics": provenance_metrics,
            "margin": {
                "margin_pct": float(margin_pct),
                "source": margin_source,
            },
            "provider_cost_micros": total_provider_cost,
            "billed_cost_micros": billed_cost,
        }

        return total_provider_cost, billed_cost, provenance

    @staticmethod
    def _find_card(
        tenant, provider: str, event_type: str, properties: Dict, as_of,
    ) -> Optional[Card]:
        cards = Card.objects.filter(
            tenant=tenant,
            provider=provider,
            event_type=event_type,
            status="active",
        )

        matched = []
        for card in cards:
            if PricingService._dimensions_match(card.dimensions, properties):
                matched.append(card)

        if not matched:
            return None

        matched.sort(
            key=lambda c: len(c.dimensions) if c.dimensions else 0,
            reverse=True,
        )
        return matched[0]

    @staticmethod
    def _find_rate(card: Card, metric_name: str, as_of) -> Optional[Rate]:
        return card.rates.filter(
            metric_name=metric_name,
            valid_from__lte=as_of,
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)
        ).order_by("-valid_from").first()

    @staticmethod
    def _dimensions_match(card_dimensions: Dict, event_properties: Dict) -> bool:
        if not card_dimensions:
            return True
        return all(
            event_properties.get(k) == v for k, v in card_dimensions.items()
        )

    @staticmethod
    def _resolve_margin(
        tenant, event_type: str, provider: str, group: str = None, as_of=None,
    ) -> Tuple[Decimal, str]:
        as_of = as_of or timezone.now()
        base = TenantMarkup.objects.filter(
            tenant=tenant,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))

        # 1. Card-level TenantMarkup (event_type + provider)
        card_markup = base.filter(
            event_type=event_type, provider=provider,
        ).order_by("-valid_from").first()
        if card_markup:
            return card_markup.margin_pct, f"tenant_markup:{card_markup.id}"

        # 2-3. Group margin (walk parent chain)
        if group:
            from apps.platform.groups.models import Group as GroupModel
            try:
                grp = GroupModel.objects.get(
                    tenant=tenant, slug=group, status="active",
                )
                current = grp
                while current is not None:
                    if current.margin_pct is not None:
                        return current.margin_pct, f"group:{current.id}"
                    current = current.parent
            except GroupModel.DoesNotExist:
                pass

        # 4. Event-type TenantMarkup
        et_markup = base.filter(
            event_type=event_type, provider="",
        ).order_by("-valid_from").first()
        if et_markup:
            return et_markup.margin_pct, f"tenant_markup:{et_markup.id}"

        # 5. Global TenantMarkup
        global_markup = base.filter(
            event_type="", provider="",
        ).order_by("-valid_from").first()
        if global_markup:
            return global_markup.margin_pct, f"tenant_markup:{global_markup.id}"

        # 6. No margin configured
        return Decimal("0"), "default:passthrough"

    @staticmethod
    def _apply_margin(provider_cost_micros: int, margin_pct: Decimal) -> int:
        if margin_pct <= 0:
            return provider_cost_micros
        divisor = Decimal("1") - (margin_pct / Decimal("100"))
        return int(
            (Decimal(provider_cost_micros) / divisor).quantize(Decimal("1"))
        )
