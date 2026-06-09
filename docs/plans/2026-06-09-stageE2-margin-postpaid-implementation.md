# Stage E2 — Accounts & Seats: Margin Rollup + Postpaid Consolidated Invoice

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make postpaid invoicing hierarchy-aware (one consolidated `CustomerUsageInvoice` per **business**, itemised **per seat**, on the business's Stripe subscription) and add a business **margin rollup** (sum of its seats). Individuals are unchanged.

**Architecture:** `aggregate_lines` gains a business scope (aggregate `UsageEvent`s across the business's seats, one line per seat); the period-close resolves seats → their business as the invoice target (seats are never invoiced directly); `MarginService` gains `compute_business` (sum of per-seat `compute_live`).

**Tech Stack:** Django 6, django-ninja, Celery, Stripe (mocked), pytest-django, SDK.

**Design ref:** `docs/plans/2026-06-09-stageE-accounts-seats-design.md` §6–§7. Builds on **E1** (hierarchy + resolver, done).

---

## ⚠️ Caveats

- **No new migration.** Pure logic on existing models (`Customer` hierarchy from E1, `CustomerUsageInvoice` keyed on `(customer, period)`).
- **Backward-compat:** for an individual/standalone customer, `aggregate_lines` + the close behave exactly as today (the business branch only engages for `account_type=="business"`).
- Stripe is **mocked** (`stripe_call`/`stripe.*` patched).

## Conventions

- Run from `ubb-platform/`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline: **703 platform + 150 SDK green.** Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: `aggregate_lines` — business scope (per-seat line items)

**Files:** Modify `apps/billing/invoicing/services/postpaid_service.py`; Test `apps/billing/invoicing/tests/test_postpaid_business.py`.

- [ ] **Step 1 — Failing test** `apps/billing/invoicing/tests/test_postpaid_business.py`:
```python
import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
def test_business_aggregates_across_seats_one_line_per_seat():
    t = Tenant.objects.create(name="T", billing_mode="postpaid")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1",
                              provider_cost_micros=1, billed_cost_micros=800_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2",
                              provider_cost_micros=1, billed_cost_micros=300_000)
    total, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert total == 1_100_000 and sum(a for _, a in lines) == total
    assert dict(lines)["alice"] == 800_000 and dict(lines)["bob"] == 300_000
```

- [ ] **Step 2 — Run** → FAIL (business has no own UsageEvents → 0).

- [ ] **Step 3 — Implement.** In `apps/billing/invoicing/services/postpaid_service.py` `aggregate_lines`, add a business branch at the **top** of the method (before the `group_by` logic):
```python
    @staticmethod
    def aggregate_lines(tenant, customer, period_start, period_end):
        """(total_micros, [(label, amount_micros), ...]); lines ALWAYS sum to total.
        A BUSINESS aggregates across its seats with one line per seat (external_id)."""
        from apps.metering.usage.models import UsageEvent
        if customer.account_type == "business":
            seats = {s.id: s.external_id for s in customer.seats.all()}
            if not seats:
                return 0, []
            qs = UsageEvent.objects.filter(
                tenant=tenant, customer_id__in=list(seats.keys()),
                effective_at__date__gte=period_start, effective_at__date__lt=period_end)
            agg = defaultdict(int)
            for cid, billed in qs.values_list("customer_id", "billed_cost_micros"):
                agg[seats.get(cid, "(seat)")] += billed or 0
            lines = sorted(agg.items(), key=lambda kv: -kv[1])
            total = sum(a for _, a in lines)
            return total, lines
        # ... existing individual logic unchanged below ...
```
(Leave the rest of the method — the `PostpaidUsageConfig`/`group_by` per-customer logic — exactly as is.)

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/invoicing/tests/test_postpaid_business.py apps/billing/invoicing -q` → green (existing individual postpaid tests unchanged + new). **Commit:** `feat(accounts): postpaid aggregate_lines aggregates a business across its seats`.

---

### Task 2: Period-close resolves seats → business invoice target

**Files:** Modify `apps/billing/invoicing/tasks.py` (`close_postpaid_usage_periods`); Test `apps/billing/invoicing/tests/test_postpaid_business.py` (append).

- [ ] **Step 1 — Failing test** (append):
```python
def test_close_invoices_business_once_with_per_seat_lines(db=None):
    pass  # replaced below


@pytest.mark.django_db
def test_close_rolls_seats_into_one_business_invoice():
    from unittest.mock import patch, MagicMock
    from django.utils import timezone
    from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
    from apps.billing.invoicing.models import CustomerUsageInvoice
    t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="postpaid",
                              stripe_connected_account_id="acct_x")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated", stripe_customer_id="cus_biz")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    start, end = _prior_month()
    for seat, key, amt in [(s1, "i1", 800_000), (s2, "i2", 300_000)]:
        ev = UsageEvent.objects.create(tenant=t, customer=seat, request_id="r", idempotency_key=key,
                                       provider_cost_micros=1, billed_cost_micros=amt)
        UsageEvent.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
    with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
         patch("apps.platform.events.tasks.process_single_event"):
        mock_sc.return_value = MagicMock(id="obj_1")
        close_postpaid_usage_periods()
    invs = CustomerUsageInvoice.objects.filter(tenant=t)
    assert invs.count() == 1                       # ONE invoice, keyed on the business
    inv = invs.first()
    assert str(inv.customer_id) == str(biz.id) and inv.total_billed_micros == 1_100_000
    assert inv.line_items.count() == 2             # one line per seat
    # seats are NOT invoiced directly
    assert not CustomerUsageInvoice.objects.filter(customer__in=[s1, s2]).exists()
```
(Delete the placeholder `test_close_invoices_business_once_with_per_seat_lines` stub — it's only there to avoid an empty edit; do not keep it.)

- [ ] **Step 2 — Run** → FAIL (today the close pushes per-seat).

- [ ] **Step 3 — Implement.** In `apps/billing/invoicing/tasks.py` `close_postpaid_usage_periods`, resolve invoice targets (seat → business, else self) before pushing:
```python
    start, end = _prior_month()
    for tenant in Tenant.objects.filter(billing_mode="postpaid", is_active=True):
        cust_ids = (UsageEvent.objects.filter(
            tenant=tenant, effective_at__date__gte=start, effective_at__date__lt=end)
            .values_list("customer_id", flat=True).distinct())
        targets = set()
        for c in Customer.objects.filter(id__in=list(cust_ids)):
            targets.add(c.parent_id if (c.account_type == "seat" and c.parent_id) else c.id)
        for target in Customer.objects.filter(id__in=list(targets)):
            try:
                PostpaidUsageService.push_customer_period(tenant, target, start, end)
            except Exception:
                logger.exception("postpaid.close_failed",
                                 extra={"data": {"customer_id": str(target.id)}})
```
> `push_customer_period(tenant, business, ...)` already keys `CustomerUsageInvoice` on the target and uses the target's `stripe_customer_id` + `StripeSubscription` — so the business's. `aggregate_lines` (Task 1) aggregates its seats. The invariant `Σ line_item == total_billed` holds across seats.

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/invoicing -q` → green (individual close tests unchanged + new business test). **Commit:** `feat(accounts): postpaid close rolls seats into one business invoice`.

---

### Task 3: Business margin rollup + endpoint + SDK

**Files:** Modify `apps/subscriptions/economics/services.py`, `apps/subscriptions/api/margin_endpoints.py`, the SDK margin client; Test `apps/subscriptions/tests/test_business_margin.py`, `ubb-sdk/tests/test_business_margin_client.py`.

- [ ] **Step 1 — Failing test** `apps/subscriptions/tests/test_business_margin.py`:
```python
import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.subscriptions.economics.services import MarginService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
def test_compute_business_sums_seats():
    t = Tenant.objects.create(name="T", billing_mode="postpaid")  # postpaid → revenue_mode billed
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1",
                              provider_cost_micros=200_000, billed_cost_micros=500_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2",
                              provider_cost_micros=100_000, billed_cost_micros=300_000)
    d = MarginService.compute_business(t.id, biz, PS, PE)
    assert d["totals"]["gross_margin_micros"] == 500_000  # (500k+300k billed) − (200k+100k provider)
    assert len(d["seats"]) == 2
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3a — `compute_business`** in `apps/subscriptions/economics/services.py` (add to `MarginService`):
```python
    @staticmethod
    def compute_business(tenant_id, business, start_date, end_date) -> dict:
        seats = list(business.seats.all())
        per_seat = [MarginService.compute_live(tenant_id, s.id, start_date, end_date) for s in seats]
        keys = ["subscription_revenue_micros", "usage_revenue_micros", "provider_cost_micros",
                "total_revenue_micros", "gross_margin_micros", "event_count"]
        totals = {k: 0 for k in keys}
        for d in per_seat:
            for k in keys:
                totals[k] += d.get(k, 0) or 0
        return {"business_id": str(business.id), "external_id": business.external_id,
                "totals": totals, "seats": per_seat}
```

- [ ] **Step 3b — Endpoint** `apps/subscriptions/api/margin_endpoints.py` — add **before** the `/{customer_id}` catch-all routes (so "business" isn't parsed as a customer UUID):
```python
@margin_api.get("/business/{external_id}")
def business_margin(request, external_id: str, start_date: date = None, end_date: date = None):
    _product_check(request)
    biz = get_object_or_404(Customer, tenant=request.auth.tenant,
                            external_id=external_id, account_type="business")
    s, e = _window(start_date, end_date)
    return MarginService.compute_business(request.auth.tenant.id, biz, s, e)
```

- [ ] **Step 3c — Endpoint test** (append to `apps/subscriptions/tests/test_business_margin.py`): with a Bearer key (mirror `test_margin_endpoints.py`), GET the margin API's `/business/biz` → 200 with `totals.gross_margin_micros` and a `seats` list. (Find the margin API URL prefix from `test_margin_endpoints.py`.)

- [ ] **Step 3d — SDK** — read the existing `get_customer_margin` in the SDK (`git grep -n "def get_customer_margin" ubb-sdk/`) to match its module/helper/prefix; add `get_business_margin(external_id)` → GET `<margin-prefix>/business/{external_id}`. Test `ubb-sdk/tests/test_business_margin_client.py` (mock the httpx client; assert path; mirror `test_rate_card_client.py`).

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/subscriptions -q` → green; from `ubb-sdk/` (no `DJANGO_SETTINGS_MODULE`): `<venv python> -m pytest -q` → green. **Commit (repo root):** `feat(accounts): business margin rollup endpoint + SDK`.

---

### Task 4: Final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected" (no new migration in E2).
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate`; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **E2 e2e spot-check:** a postpaid business with 2 seats (each with usage) → the close produces **one** `CustomerUsageInvoice` keyed on the **business**, with a **per-seat line item**, `Σ line_item == total_billed`, and seats are not invoiced directly; `GET /business/{ext}` margin = sum of the seats; individuals invoice + margin exactly as today.

---

## Self-Review

**Spec coverage (E2 = design §6–§7):** business `aggregate_lines` across seats, line-per-seat (T1) ✓; close rolls seats → one business invoice keyed on the business, seats not invoiced directly (T2) ✓; `Σ line_item == total_billed` (T1/T2 asserts) ✓; business margin rollup = sum of seats + endpoint + SDK (T3) ✓; individuals unchanged (T1/T2/T4) ✓; no migration (T4) ✓.

**Placeholder scan:** T2's placeholder stub is explicitly flagged for deletion; T3d says "read get_customer_margin to match prefix" with a concrete `git grep`. No TBD/TODO.

**Type/name consistency:** `aggregate_lines` business branch returns `(total, [(seat_external_id, amount), ...])` consistent with the existing `(total, lines)` contract used by `push_customer_period` (T1↔T2). `compute_business(tenant_id, business, start, end) -> {business_id, external_id, totals, seats}` defined T3a, used by the endpoint T3b + SDK T3d. The close target resolution (seat→parent_id) uses the E1 `account_type`/`parent` fields.
