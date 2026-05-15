"""Snapshot resolved margins into explicit Rate.cost_per_unit_micros.

Before this migration: rate.cost_per_unit_micros held provider cost; margin
was applied at runtime via TenantMarkup + Group.margin_pct cascade.

After: rate.provider_cost_per_unit_micros holds provider cost; rate.cost_per_unit_micros
holds the tenant-facing billed price (provider cost after margin).
"""

from decimal import Decimal

from django.db import migrations


def _resolve_margin(Rate, TenantMarkup, Group, rate):
    """Historical resolver, inlined so we don't depend on services code."""
    card = rate.card
    tenant = card.tenant
    base = TenantMarkup.objects.filter(tenant=tenant, valid_to__isnull=True)

    card_markup = base.filter(event_type=card.event_type, provider=card.provider).order_by("-valid_from").first()
    if card_markup:
        return card_markup.margin_pct

    et_markup = base.filter(event_type=card.event_type, provider="").order_by("-valid_from").first()
    if et_markup:
        return et_markup.margin_pct

    global_markup = base.filter(event_type="", provider="").order_by("-valid_from").first()
    if global_markup:
        return global_markup.margin_pct

    if card.group_id:
        current = card.group
        while current is not None:
            if current.margin_pct is not None:
                return current.margin_pct
            current = current.parent

    return Decimal("0")


def _apply_margin(provider_cost, margin_pct):
    if margin_pct <= 0:
        return provider_cost
    divisor = Decimal("1") - (margin_pct / Decimal("100"))
    return int((Decimal(provider_cost) / divisor).quantize(Decimal("1")))


def backfill_forward(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    TenantMarkup = apps.get_model("pricing", "TenantMarkup")
    Group = apps.get_model("groups", "Group")

    for rate in Rate.objects.select_related("card", "card__tenant", "card__group").iterator():
        if rate.provider_cost_per_unit_micros is not None:
            continue  # already migrated
        provider_cost = rate.cost_per_unit_micros
        margin_pct = _resolve_margin(Rate, TenantMarkup, Group, rate)
        billed = _apply_margin(provider_cost, margin_pct)
        rate.provider_cost_per_unit_micros = provider_cost
        rate.cost_per_unit_micros = billed
        rate.save(update_fields=["provider_cost_per_unit_micros", "cost_per_unit_micros"])


def backfill_reverse(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    for rate in Rate.objects.iterator():
        if rate.provider_cost_per_unit_micros is not None:
            rate.cost_per_unit_micros = rate.provider_cost_per_unit_micros
            rate.provider_cost_per_unit_micros = None
            rate.save(update_fields=["provider_cost_per_unit_micros", "cost_per_unit_micros"])


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_rate_provider_cost"),
        ("groups", "0001_initial"),
    ]
    operations = [migrations.RunPython(backfill_forward, backfill_reverse)]
