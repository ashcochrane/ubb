# Pricing Stage A — Rate-Card Pricing Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reinstate a tenant-defined rate-card pricing engine — two optional card types (cost + price) in one `RateCard` table — that resolves to the existing `provider_cost_micros`/`billed_cost_micros` fields inside `record_usage`, so usage can be priced from units (`usage_metrics`) while every downstream contract (drawdown, margin, postpaid) is preserved unchanged.

**Architecture:** A single `RateCard` model (cost|price, per_unit|flat, dimensional matching with most-specific-wins + wildcard, valid_from/valid_to versioning, per-row currency). A new `PricingService.price()` implements the full resolution ladder (caller-cost → cost card → 0; caller-billed → price card → markup → provider) and absorbs the existing `MarkupService`. It is called at the single choke point `UsageService.record_usage`, before the event is written, so cost-consistency holds by construction. Additive + backward-compatible: zero cards configured → identical to today.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres, SDK (httpx).

**Design ref:** `docs/plans/2026-06-08-pricing-stageA-rate-card-engine-design.md`

---

## ⚠️ Caveats

- **Contract change:** `RecordUsageRequest.provider_cost_micros` and `UsageService.record_usage(provider_cost_micros=...)` go from **required → optional** (Task 4). If any existing test asserts "422 when provider_cost_micros missing," update it — the new contract is optional (missing → priced from cards or 0). Existing callers that pass it behave identically.
- **Invariant (must never regress):** after pricing resolution, `UsageRecorded.cost_micros == billed_cost_micros` and `provider_cost_micros` is always a concrete int (default 0). Tasks 3–4 include cost-contract tests.
- **Migrations** (Tasks 1, 2): use `makemigrations <app>` then `makemigrations --check --dry-run` (expect "No changes detected") then `migrate`. Three additive migrations total; DB-validate each.

## Conventions

- Run from `ubb-platform/`. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run`. DB: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`.
- Baseline: **655 platform + 136 SDK green.** Branch `tl-changes-05-06-26`. Commit per task; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Migration heads: pricing `0006_slim_tenant_markup`, usage `0018_collapse_cost_model`, tenants `0009_tenant_default_currency`.

---

### Task 1: `RateCard` model (cost+price, per_unit+flat, dimensional, versioned)

**Files:** Modify `apps/metering/pricing/models.py`; Create migration `apps/metering/pricing/migrations/0007_ratecard.py` (via makemigrations); Test `apps/metering/pricing/tests/test_rate_card_model.py`.

- [ ] **Step 1 — Failing test** `apps/metering/pricing/tests/test_rate_card_model.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestRateCard:
    def test_dimensions_hash_and_per_unit_compute(self):
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        c = RateCard.objects.create(
            tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", dimensions={"model": "gpt-4"},
            pricing_model="per_unit", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        assert c.dimensions_hash and len(c.dimensions_hash) == 64
        # 1000 units @ 5000/1e6, round-half-up: (1000*5000 + 500000)//1000000 = 5
        assert c.compute(1000) == 5
        # round-half-up midpoint
        c2 = RateCard.objects.create(tenant=t, card_type="cost", metric_name="m",
                                     rate_per_unit_micros=1, unit_quantity=2)
        assert c2.compute(1) == 1 and c2.compute(0) == 0

    def test_flat_compute_uses_fixed(self):
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        c = RateCard.objects.create(tenant=t, card_type="price", metric_name="seats",
                                    pricing_model="flat", fixed_micros=2_000_000)
        assert c.compute(5) == 2_000_000  # flat ignores units

    def test_one_active_tenant_default_per_slice(self):
        from django.db.utils import IntegrityError
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", metric_name="input_tokens")
        with pytest.raises(IntegrityError):
            RateCard.objects.create(tenant=t, card_type="cost", provider="openai",
                                    event_type="chat", metric_name="input_tokens")
```

- [ ] **Step 2 — Run** → FAIL (no `RateCard`).

- [ ] **Step 3 — Model** append to `apps/metering/pricing/models.py` (file already imports `from django.db import models` + `from core.models import BaseModel`; add `import hashlib` and `import json` at top):
```python
CARD_TYPE_CHOICES = [("cost", "Cost"), ("price", "Price")]
PRICING_MODEL_CHOICES = [("per_unit", "Per unit"), ("flat", "Flat")]


class RateCard(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="rate_cards")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_cards", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    metric_name = models.CharField(max_length=100)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    pricing_model = models.CharField(max_length=20, choices=PRICING_MODEL_CHOICES, default="per_unit")
    rate_per_unit_micros = models.BigIntegerField(default=0)
    unit_quantity = models.BigIntegerField(default=1_000_000)
    fixed_micros = models.BigIntegerField(default=0)
    tiers = models.JSONField(default=list, blank=True)  # headroom for tiered/volume/package
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="")
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_rate_card"
        indexes = [
            models.Index(fields=["tenant", "card_type", "provider", "event_type", "metric_name"],
                         name="idx_ratecard_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=True),
                name="uq_ratecard_active_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "customer", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=False),
                name="uq_ratecard_active_customer"),
        ]

    def save(self, *args, **kwargs):
        self.dimensions_hash = hashlib.sha256(
            json.dumps(self.dimensions or {}, sort_keys=True).encode()).hexdigest()
        super().save(*args, **kwargs)

    def compute(self, units):
        """Cost/price in micros for `units` of this metric. Round-half-up per-unit; flat ignores units."""
        if self.pricing_model == "flat":
            return self.fixed_micros
        units = units or 0
        return (units * self.rate_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity + self.fixed_micros
```

- [ ] **Step 4 — Migration:** `$DJ manage.py makemigrations pricing` (creates `0007_ratecard`); then `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 5 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/metering/pricing/tests/test_rate_card_model.py -q` → green. **Commit:** `feat(pricing): RateCard model (cost+price, per_unit+flat, versioned)`.

---

### Task 2: schema columns — `usage_metrics` on UsageEvent + `require_cost_card_coverage` on Tenant

**Files:** Modify `apps/metering/usage/models.py`, `apps/platform/tenants/models.py`; migrations `apps/metering/usage/migrations/0019_*`, `apps/platform/tenants/migrations/0010_*`; Test `apps/metering/usage/tests/test_usage_metrics_field.py`.

- [ ] **Step 1 — Failing test** `apps/metering/usage/tests/test_usage_metrics_field.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_usage_event_stores_usage_metrics_and_tenant_flag_default():
    t = Tenant.objects.create(name="T")
    assert t.require_cost_card_coverage is False
    c = Customer.objects.create(tenant=t, external_id="c1")
    e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  usage_metrics={"input_tokens": 1500})
    e.refresh_from_db()
    assert e.usage_metrics == {"input_tokens": 1500}
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Add columns.** In `apps/metering/usage/models.py`, after `pricing_provenance` (line 27) add:
```python
    usage_metrics = models.JSONField(default=dict, blank=True)
```
In `apps/platform/tenants/models.py` on `Tenant`, add:
```python
    require_cost_card_coverage = models.BooleanField(default=False)
```

- [ ] **Step 4 — Migrations:** `$DJ manage.py makemigrations usage tenants`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 5 — Verify:** `$DJ -m pytest apps/metering/usage/tests/test_usage_metrics_field.py -q` → green. **Commit:** `feat(metering): usage_metrics column + tenant require_cost_card_coverage`.

---

### Task 3: `PricingService` — resolver + the resolution ladder + provenance

**Files:** Create `apps/metering/pricing/services/pricing_service.py`; Test `apps/metering/pricing/tests/test_pricing_service.py`.

- [ ] **Step 1 — Failing tests** `apps/metering/pricing/tests/test_pricing_service.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard, TenantMarkup
from apps.metering.pricing.services.pricing_service import PricingService, PricingError


@pytest.mark.django_db
class TestPricing:
    def _t(self, **kw):
        return Tenant.objects.create(name="T", **kw)

    def test_caller_cost_wins_then_markup(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, markup_percentage_micros=20_000_000)  # +20%
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=1_000_000, caller_billed=None)
        assert prov == 1_000_000 and billed == 1_200_000 and p["price_source"] == "markup"

    def test_cost_card_computes_provider_when_no_caller_cost(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", dimensions={"model": "gpt-4"},
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics={"input_tokens": 1000}, tags={"model": "gpt-4"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 5  # no markup → billed == provider

    def test_price_card_charges_on_different_metric(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        RateCard.objects.create(tenant=t, card_type="price", provider="openai", event_type="chat",
            metric_name="seats", pricing_model="flat", fixed_micros=9_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics={"input_tokens": 1000, "seats": 3}, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 9_000_000 and p["price_source"] == "rate_card"

    def test_most_specific_dimension_wins_and_wildcard_fallback(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        RateCard.objects.create(tenant=t, card_type="cost", provider="o", event_type="e",
            metric_name="tok", dimensions={}, rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        RateCard.objects.create(tenant=t, card_type="cost", provider="o", event_type="e",
            metric_name="tok", dimensions={"model": "gpt-4"}, rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        prov, _, _ = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 1_000_000}, tags={"model": "gpt-4"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 9_000  # specific wins
        prov2, _, _ = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 1_000_000}, tags={"model": "other"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov2 == 1_000  # falls back to wildcard

    def test_missing_cost_card_permissive_zero_then_strict_raises(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        prov, billed, p = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 100}, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 0 and p["uncosted_metrics"] == ["tok"]
        t.require_cost_card_coverage = True; t.save(update_fields=["require_cost_card_coverage"])
        with pytest.raises(PricingError):
            PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
                usage_metrics={"tok": 100}, tags=None, currency="usd",
                caller_provider_cost=None, caller_billed=None)
```

- [ ] **Step 2 — Run** → FAIL (no module).

- [ ] **Step 3 — Implement** `apps/metering/pricing/services/pricing_service.py`:
```python
from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import RateCard

PRICING_ENGINE_VERSION = "2.0.0"


class PricingError(Exception):
    pass


class PricingService:
    @staticmethod
    def _dimensions_match(card_dimensions, tags):
        tags = tags or {}
        for k, v in (card_dimensions or {}).items():
            if str(tags.get(k)) != str(v):
                return False
        return True

    @staticmethod
    def _resolve_card(tenant, customer, card_type, provider, event_type, metric_name, tags, currency, as_of):
        base = list(RateCard.objects.filter(
            tenant=tenant, card_type=card_type, provider=provider or "", event_type=event_type or "",
            metric_name=metric_name, currency=currency, valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)))
        owners = ([customer.id] if customer is not None else []) + [None]
        for owner in owners:
            cands = [c for c in base if c.customer_id == owner
                     and PricingService._dimensions_match(c.dimensions, tags)]
            if cands:
                cands.sort(key=lambda c: (len(c.dimensions or {}), c.valid_from), reverse=True)
                return cands[0]
        return None

    @staticmethod
    def price(*, tenant, customer, event_type, provider, usage_metrics, tags, currency,
              caller_provider_cost, caller_billed, as_of=None):
        as_of = as_of or timezone.now()
        usage_metrics = usage_metrics or {}
        prov = {"engine_version": PRICING_ENGINE_VERSION, "metrics": []}

        # ---- COST ----
        if caller_provider_cost is not None:
            provider_cost = caller_provider_cost
            prov["cost_source"] = "caller"
        else:
            provider_cost = 0
            uncosted = []
            for metric, units in usage_metrics.items():
                card = PricingService._resolve_card(tenant, customer, "cost", provider,
                                                    event_type, metric, tags, currency, as_of)
                if card is None:
                    uncosted.append(metric)
                    continue
                amt = card.compute(units)
                provider_cost += amt
                prov["metrics"].append({"metric": metric, "units": units, "card_type": "cost",
                    "rate_card_id": str(card.id), "pricing_model": card.pricing_model, "micros": amt})
            prov["cost_source"] = "rate_card"
            if uncosted:
                prov["uncosted_metrics"] = uncosted
                if getattr(tenant, "require_cost_card_coverage", False):
                    raise PricingError(f"No cost rate card for metrics: {uncosted}")

        # ---- PRICE ----
        if caller_billed is not None:
            billed = caller_billed
            prov["price_source"] = "caller"
        else:
            price_total, matched = 0, False
            for metric, units in usage_metrics.items():
                card = PricingService._resolve_card(tenant, customer, "price", provider,
                                                    event_type, metric, tags, currency, as_of)
                if card is None:
                    continue
                matched = True
                amt = card.compute(units)
                price_total += amt
                prov["metrics"].append({"metric": metric, "units": units, "card_type": "price",
                    "rate_card_id": str(card.id), "pricing_model": card.pricing_model, "micros": amt})
            if matched:
                billed = price_total
                prov["price_source"] = "rate_card"
            else:
                from apps.metering.pricing.services.markup_service import MarkupService
                billed = MarkupService.apply(provider_cost, tenant=tenant, customer=customer)
                prov["price_source"] = "markup"

        prov["provider_cost_micros"] = provider_cost
        prov["billed_cost_micros"] = billed
        return provider_cost, billed, prov
```

- [ ] **Step 4 — Verify:** `$DJ -m pytest apps/metering/pricing/tests/test_pricing_service.py -q` → green. **Commit:** `feat(pricing): PricingService resolution ladder (cost/price cards + markup)`.

---

### Task 4: Integrate into `record_usage` + intake schema + endpoint

**Files:** Modify `apps/metering/usage/services/usage_service.py`, `api/v1/schemas.py`, `api/v1/metering_endpoints.py`; Test `apps/metering/usage/tests/test_record_usage_pricing.py`.

- [ ] **Step 1 — Failing tests** `apps/metering/usage/tests/test_record_usage_pricing.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestRecordUsagePricing:
    def test_backward_compat_caller_cost_unchanged(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=4_000)
        assert r["provider_cost_micros"] == 4_000 and r["billed_cost_micros"] == 4_000

    def test_priced_from_cost_card_when_no_caller_cost(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=None,
            provider="openai", event_type="chat", usage_metrics={"input_tokens": 1000})
        assert r["provider_cost_micros"] == 5 and r["billed_cost_micros"] == 5
        from apps.metering.usage.models import UsageEvent
        e = UsageEvent.objects.get(id=r["event_id"])
        assert e.usage_metrics == {"input_tokens": 1000}
        assert e.pricing_provenance["cost_source"] == "rate_card"
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3a — `record_usage`** in `apps/metering/usage/services/usage_service.py`: change the signature default `provider_cost_micros` to `None`, add `usage_metrics=None`, and replace the markup block (lines 60-62) with the PricingService call. The method becomes:
```python
    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros=None, billed_cost_micros=None, units=None,
                     provider="", event_type="", currency=None, tags=None,
                     product_id="", metadata=None, run_id=None, usage_metrics=None):
        validate_tags(tags)
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            return _result(existing, run_total=None)
        currency = currency or tenant.default_currency
        from apps.metering.pricing.services.pricing_service import PricingService
        provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
            tenant=tenant, customer=customer, event_type=event_type or "", provider=provider or "",
            usage_metrics=usage_metrics, tags=tags, currency=currency,
            caller_provider_cost=provider_cost_micros, caller_billed=billed_cost_micros)
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService
            run = RunService.accumulate_cost(run_id, billed_cost_micros)
        try:
            with transaction.atomic():
                event = UsageEvent.objects.create(
                    tenant=tenant, customer=customer, request_id=request_id,
                    idempotency_key=idempotency_key, metadata=metadata or {},
                    event_type=event_type or "", provider=provider or "",
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    units=units, currency=currency, usage_metrics=usage_metrics or {},
                    pricing_provenance=provenance,
                    product_id=product_id or "", tags=tags, run_id=run_id)
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            return _result(existing, run_total=None)
        write_event(UsageRecorded(
            tenant_id=str(tenant.id), customer_id=str(customer.id), event_id=str(event.id),
            cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros, event_type=event_type or "",
            provider=provider or "", run_id=str(run_id) if run_id else None))
        return _result(event, run_total=run.total_cost_micros if run else None)
```

- [ ] **Step 3b — Schema** `api/v1/schemas.py` `RecordUsageRequest`: change `provider_cost_micros` to optional and add `usage_metrics`:
```python
    provider_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
```
```python
    usage_metrics: Optional[dict[str, int]] = None
```

- [ ] **Step 3c — Endpoint** `api/v1/metering_endpoints.py` `record_usage`: pass `usage_metrics=payload.usage_metrics` into `UsageService.record_usage(...)`, and wrap the call to translate `PricingError` → 422. Add near the top of the `try`:
```python
    from apps.metering.pricing.services.pricing_service import PricingError
```
and add this `except` beside the existing `HardStopExceeded` handler:
```python
    except PricingError as e:
        return metering_api.create_response(
            request, {"error": "pricing_error", "detail": str(e)}, status=422)
```

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/metering api/v1 -q` → green (existing usage tests + new). If any test asserted `provider_cost_micros` required, update it to the new optional contract. **Commit:** `feat(metering): price usage via rate cards at the record_usage choke point`.

---

### Task 5: Expose `pricing_provenance` + `usage_metrics` in the usage response

**Files:** Modify `apps/metering/usage/services/usage_service.py` (`_result`), `api/v1/schemas.py` (`RecordUsageResponse`); Test `api/v1/tests/test_record_usage_provenance.py`.

- [ ] **Step 1 — Failing test** `api/v1/tests/test_record_usage_provenance.py`: POST `/api/v1/usage` with a cost card configured + `usage_metrics` (no `provider_cost_micros`) and assert the JSON response includes `pricing_provenance` with `cost_source == "rate_card"` and `usage_metrics` echoed. (Mirror the existing metering endpoint test setup: tenant `products=["metering"]`, `TenantApiKey.create_key`, Bearer.)
- [ ] **Step 2 — Run** → FAIL (keys absent).
- [ ] **Step 3 — Implement.** In `_result` (usage_service.py) add two keys:
```python
        "usage_metrics": event.usage_metrics,
        "pricing_provenance": event.pricing_provenance,
```
In `RecordUsageResponse` (`api/v1/schemas.py`) add:
```python
    usage_metrics: Optional[dict] = None
    pricing_provenance: Optional[dict] = None
```
- [ ] **Step 4 — Verify:** `$DJ -m pytest api/v1/tests/test_record_usage_provenance.py -q` → green. **Commit:** `feat(metering): expose pricing_provenance + usage_metrics in usage response`.

---

### Task 6: Rate-card CRUD API (soft-versioned, gated cost→metering / price→billing)

**Files:** Modify `api/v1/schemas.py`, `api/v1/metering_endpoints.py`; Test `api/v1/tests/test_rate_card_crud.py`.

- [ ] **Step 1 — Failing tests** `api/v1/tests/test_rate_card_crud.py`: with a `products=["metering","billing"]` tenant + Bearer key: POST a cost card → 200 with an `id`; GET `/pricing/rate-cards` lists it; PUT `/pricing/rate-cards/{id}` returns a NEW id and the old is no longer listed (soft-versioned); DELETE soft-expires (no longer listed). Also: a `products=["metering"]`-only tenant POSTing a `card_type="price"` card → 403.
- [ ] **Step 2 — Run** → FAIL (404).
- [ ] **Step 3a — Schemas** `api/v1/schemas.py` (append):
```python
class RateCardIn(Schema):
    card_type: str
    metric_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    dimensions: dict = Field(default_factory=dict)
    pricing_model: str = "per_unit"
    rate_per_unit_micros: int = Field(default=0, ge=0)
    unit_quantity: int = Field(default=1_000_000, gt=0)
    fixed_micros: int = Field(default=0, ge=0)
    currency: str = Field(default="usd", max_length=3)
    product_id: str = Field(default="", max_length=100)
    customer_id: Optional[UUID] = None

class RateCardOut(Schema):
    id: str
    card_type: str
    metric_name: str
    provider: str
    event_type: str
    dimensions: dict
    pricing_model: str
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    currency: str
    product_id: str
    customer_id: Optional[str] = None
    valid_from: str
    valid_to: Optional[str] = None
```
Add `RateCardIn, RateCardOut` to the `from api.v1.schemas import (...)` block in `metering_endpoints.py`.
- [ ] **Step 3b — Endpoints** `api/v1/metering_endpoints.py` (append; add `from apps.metering.pricing.models import RateCard` and `from django.utils import timezone`; `_product_check`/`UUID`/`get_object_or_404`/`Customer` already imported):
```python
_billing_check = ProductAccess("billing")


def _rate_card_to_out(c):
    return {"id": str(c.id), "card_type": c.card_type, "metric_name": c.metric_name,
            "provider": c.provider, "event_type": c.event_type, "dimensions": c.dimensions,
            "pricing_model": c.pricing_model, "rate_per_unit_micros": c.rate_per_unit_micros,
            "unit_quantity": c.unit_quantity, "fixed_micros": c.fixed_micros, "currency": c.currency,
            "product_id": c.product_id, "customer_id": str(c.customer_id) if c.customer_id else None,
            "valid_from": c.valid_from.isoformat(), "valid_to": c.valid_to.isoformat() if c.valid_to else None}


def _gate_card_type(request, card_type):
    _product_check(request)
    if card_type == "price":
        _billing_check(request)


@metering_api.get("/pricing/rate-cards", response=list[RateCardOut])
def list_rate_cards(request, card_type: str = None):
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant, valid_to__isnull=True)
    if card_type:
        qs = qs.filter(card_type=card_type)
    return [_rate_card_to_out(c) for c in qs.order_by("card_type", "provider", "event_type", "metric_name")]


@metering_api.post("/pricing/rate-cards", response=RateCardOut)
def create_rate_card(request, payload: RateCardIn):
    _gate_card_type(request, payload.card_type)
    customer = None
    if payload.customer_id:
        customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    card = RateCard.objects.create(
        tenant=request.auth.tenant, customer=customer, card_type=payload.card_type,
        metric_name=payload.metric_name, provider=payload.provider, event_type=payload.event_type,
        dimensions=payload.dimensions, pricing_model=payload.pricing_model,
        rate_per_unit_micros=payload.rate_per_unit_micros, unit_quantity=payload.unit_quantity,
        fixed_micros=payload.fixed_micros, currency=payload.currency, product_id=payload.product_id)
    return _rate_card_to_out(card)


@metering_api.put("/pricing/rate-cards/{card_id}", response=RateCardOut)
def update_rate_card(request, card_id: UUID, payload: RateCardIn):
    _gate_card_type(request, payload.card_type)
    old = get_object_or_404(RateCard, id=card_id, tenant=request.auth.tenant, valid_to__isnull=True)
    old.valid_to = timezone.now()
    old.save(update_fields=["valid_to", "updated_at"])
    customer = None
    if payload.customer_id:
        customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    card = RateCard.objects.create(
        tenant=request.auth.tenant, customer=customer, card_type=payload.card_type,
        metric_name=payload.metric_name, provider=payload.provider, event_type=payload.event_type,
        dimensions=payload.dimensions, pricing_model=payload.pricing_model,
        rate_per_unit_micros=payload.rate_per_unit_micros, unit_quantity=payload.unit_quantity,
        fixed_micros=payload.fixed_micros, currency=payload.currency, product_id=payload.product_id)
    return _rate_card_to_out(card)


@metering_api.delete("/pricing/rate-cards/{card_id}")
def delete_rate_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(RateCard, id=card_id, tenant=request.auth.tenant, valid_to__isnull=True)
    card.valid_to = timezone.now()
    card.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}
```
> Note: `save(update_fields=[...])` re-runs `RateCard.save()` which recomputes `dimensions_hash` (unchanged) — fine.
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest api/v1/tests/test_rate_card_crud.py apps/metering -q` → green. **Commit:** `feat(pricing): rate-card CRUD API (soft-versioned, gated)`.

---

### Task 7: SDK rate-card methods + type

**Files:** Modify `ubb-sdk/ubb/types.py`, `ubb-sdk/ubb/metering.py`; Test `ubb-sdk/tests/test_rate_card_client.py`.

- [ ] **Step 1 — Type** `ubb-sdk/ubb/types.py` (append; file imports `from dataclasses import dataclass`):
```python
@dataclass(frozen=True)
class RateCard:
    id: str | None = None
    card_type: str | None = None
    metric_name: str | None = None
    provider: str | None = None
    event_type: str | None = None
    dimensions: dict | None = None
    pricing_model: str | None = None
    rate_per_unit_micros: int | None = None
    unit_quantity: int | None = None
    fixed_micros: int | None = None
    currency: str | None = None
    product_id: str | None = None
    customer_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
```
- [ ] **Step 2 — `MeteringClient` methods** `ubb-sdk/ubb/metering.py` (add `RateCard` to the `from ubb.types import ...`; use the client's `self._request`):
```python
    def create_rate_card(self, *, card_type, metric_name, provider="", event_type="",
                         dimensions=None, pricing_model="per_unit", rate_per_unit_micros=0,
                         unit_quantity=1_000_000, fixed_micros=0, currency="usd",
                         product_id="", customer_id=None):
        body = {"card_type": card_type, "metric_name": metric_name, "provider": provider,
                "event_type": event_type, "dimensions": dimensions or {}, "pricing_model": pricing_model,
                "rate_per_unit_micros": rate_per_unit_micros, "unit_quantity": unit_quantity,
                "fixed_micros": fixed_micros, "currency": currency, "product_id": product_id,
                "customer_id": customer_id}
        r = self._request("post", "/api/v1/pricing/rate-cards", json=body)
        return RateCard(**r.json())

    def list_rate_cards(self, card_type=None):
        params = {"card_type": card_type} if card_type else None
        r = self._request("get", "/api/v1/pricing/rate-cards", params=params)
        return [RateCard(**row) for row in r.json()]

    def delete_rate_card(self, card_id):
        self._request("delete", f"/api/v1/pricing/rate-cards/{card_id}")
        return True
```
- [ ] **Step 3 — Tests** `ubb-sdk/tests/test_rate_card_client.py`: mock `ubb.metering.httpx.Client.post`/`.get`; assert path + that `create_rate_card` returns a `RateCard` and `list_rate_cards` parses. (Mirror `tests/test_postpaid_client.py` style; `MeteringClient(api_key=..., base_url=...)`.)
- [ ] **Step 4 — Verify:** from `ubb-sdk/` (no `DJANGO_SETTINGS_MODULE`): `<venv python> -m pytest -q` → green. **Commit (repo root):** `feat(sdk): rate-card methods`.

---

### Task 8: Final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate` applies `pricing/0007`, `usage/0019`, `tenants/0010` cleanly; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **E2E ladder spot-check:** a tenant with a gpt-4 `input_tokens` cost card + a `seats` flat price card; POST `/api/v1/usage` with `usage_metrics={"input_tokens":1500,"seats":3}`, `tags={"model":"gpt-4"}`, no `provider_cost_micros` → response `provider_cost_micros` = card cost, `billed_cost_micros` = seats price, `pricing_provenance` records both cards; a second POST with `provider_cost_micros` set → caller-cost wins. Confirm a no-cards tenant prices identically to before (backward-compat).

---

## Self-Review

**Spec coverage:** two-card model + one table (T1) ✓; per_unit+flat compute round-half-up (T1) ✓; dimensional most-specific-wins + wildcard + validity + customer-override (T3) ✓; versioning valid_from/valid_to + one-active constraint (T1) ✓; multi-metric `usage_metrics` intake + column (T2/T4) ✓; resolution ladder caller-cost→cost-card→0 and caller-billed→price-card→markup→provider (T3) ✓; markup retained as default (T3) ✓; caller-cost wins (T3/T4) ✓; permissive missing-card + opt-in strict mode (T2 flag + T3) ✓; integration at record_usage preserving invariants (T4) ✓; provenance stamping + exposure (T4/T5) ✓; CRUD soft-versioned + gating cost/price (T6) ✓; SDK (T7) ✓; backward-compat (T4/T8) ✓; per-row currency match (T3 resolver filters currency) ✓; deferred tiers = headroom only (no calculator) ✓.

**Placeholder scan:** T5/T6/T7 tests say "mirror existing style" but give exact endpoints/payloads/asserts; migrations use makemigrations with explicit verify. No TBD/TODO.

**Type/name consistency:** `RateCard` fields + `compute()` consistent T1/T3/T6/T7. `PricingService.price(...)` keyword signature identical in T3 definition and T4 caller. `PricingError` raised T3, caught T4. `pricing_provenance` keys (`cost_source`/`price_source`/`uncosted_metrics`/`metrics`) consistent T3→T4→T5. `usage_metrics` field consistent T2/T4/T5. Gating helper `_gate_card_type` + `_billing_check` consistent within T6. SDK `RateCard` dataclass matches `RateCardOut` keys.

**Migration risk:** three additive migrations (`pricing/0007`, `usage/0019`, `tenants/0010`), each DB-validated in its task + fresh-DB in T8.
