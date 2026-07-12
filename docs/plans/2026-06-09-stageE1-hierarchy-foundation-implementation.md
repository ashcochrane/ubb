# Stage E1 — Accounts & Seats: Hierarchy Foundation + Money Paths + API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the business/seats hierarchy to `Customer` and route money (wallet drawdown, suspension, auto-top-up) to the resolved billing-owner (the business for a pooled seat) while keeping control + attribution (budget cap, spend counter, `UsageEvent`, rate-limit) per-seat — backward-compatible for individuals.

**Architecture:** Three additive `Customer` fields + one `resolve_billing_owner` resolver injected at the drawdown handler and the gate. Pooled seats draw the business wallet; the existing Stage-C auto-top-up follows because `BalanceLow` now carries the owner's id. Plus orchestrator API to create businesses/seats and view a business.

**Tech Stack:** Django 6, django-ninja, pytest-django, Postgres/Redis, SDK (httpx).

**Design ref:** `docs/plans/2026-06-09-stageE-accounts-seats-design.md` (E1 = "Hierarchy foundation + money paths + API"). E2 (margin rollup + postpaid) is a separate plan after E1.

---

## ⚠️ Caveats

- **Backward-compat is sacred:** for an `individual` (and an `allocated` seat), `resolve_billing_owner` returns *self*, so every existing flow must behave byte-for-byte as today. Task 6 proves it.
- **The money-vs-control split:** the resolver governs the **wallet/suspend/auto-top-up**; `record_usage_spend`, `BudgetService.check`, `UsageEvent`, and the rate-limit key stay on the **seat**. Don't let the resolver leak into the control paths.
- One additive migration (`customers/0011`); DB-validate it.

## Conventions

- Run from `ubb-platform/`. Venv python: `/c/Users/tom_l/git/ubb/ubb-platform/.venv/Scripts/python.exe`. `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <python>`.
- Static: `$DJ manage.py check` · `$DJ manage.py makemigrations --check --dry-run`. DB: `$DJ manage.py migrate` · `$DJ -m pytest <paths> -q`.
- Baseline: **692 platform + 147 SDK green.** Branch `tl-changes-05-06-26`. Commit per task; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- customers migration head: `0010_customer_revenue_mode`.

---

### Task 1: Hierarchy fields + `resolve_billing_owner` resolver

**Files:** Modify `apps/platform/customers/models.py`; Create `apps/billing/accounts.py`; migration `customers/0011_*`; Test `apps/billing/tests/test_accounts_resolver.py`.

- [ ] **Step 1 — Failing test** `apps/billing/tests/test_accounts_resolver.py`:
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.accounts import resolve_billing_owner, resolve_billing_owner_id


@pytest.mark.django_db
class TestResolver:
    def test_individual_resolves_to_self(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")  # default account_type individual
        assert resolve_billing_owner_id(c) == c.id

    def test_pooled_seat_resolves_to_business(self):
        t = Tenant.objects.create(name="T")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert resolve_billing_owner_id(seat) == biz.id

    def test_allocated_seat_resolves_to_self(self):
        t = Tenant.objects.create(name="T")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="allocated")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert resolve_billing_owner_id(seat) == seat.id
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Fields** in `apps/platform/customers/models.py` (add the choices + 3 fields on `Customer`, e.g. after `revenue_mode`):
```python
ACCOUNT_TYPE_CHOICES = [("individual", "Individual"), ("business", "Business"), ("seat", "Seat")]
BILLING_TOPOLOGY_CHOICES = [("pooled", "Pooled"), ("allocated", "Allocated")]
```
```python
    account_type = models.CharField(max_length=12, choices=ACCOUNT_TYPE_CHOICES, default="individual", db_index=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="seats")
    billing_topology = models.CharField(max_length=10, choices=BILLING_TOPOLOGY_CHOICES, blank=True, default="")
```

- [ ] **Step 4 — Resolver** `apps/billing/accounts.py`:
```python
def resolve_billing_owner(customer):
    """The Customer whose wallet/card/auto-top-up funds this customer:
    the business for a POOLED seat, otherwise the customer itself
    (individual, allocated seat, or business)."""
    if customer.account_type == "seat" and customer.parent_id:
        parent = customer.parent
        if parent.billing_topology == "pooled":
            return parent
    return customer


def resolve_billing_owner_id(customer):
    return resolve_billing_owner(customer).id
```

- [ ] **Step 5 — Migration:** `$DJ manage.py makemigrations customers` (`0011`); `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 6 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/tests/test_accounts_resolver.py -q` → green. **Commit:** `feat(accounts): Customer hierarchy fields + resolve_billing_owner`.

---

### Task 2: Drawdown handler — money→owner, control→seat

**Files:** Modify `apps/billing/handlers.py`; Test `apps/billing/tests/test_outbox_handlers.py` (append).

- [ ] **Step 1 — Failing test** (append to `TestBillingOutboxHandler`):
```python
    def test_pooled_seat_debits_business_wallet_records_spend_on_seat(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet, WalletTransaction
        tenant = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=tenant, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=tenant, external_id="s1", account_type="seat", parent=biz)
        bw = Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload={"tenant_id": str(tenant.id), "customer_id": str(seat.id),
                     "event_id": str(uuid.uuid4()), "cost_micros": 2_000_000})
        handle_usage_recorded_billing(str(event.id), event.payload)
        bw.refresh_from_db()
        assert bw.balance_micros == 8_000_000  # the BUSINESS pool was debited
        assert not Wallet.objects.filter(customer=seat).exists()  # seat has no wallet
        # the deduction WalletTransaction is on the business wallet
        assert WalletTransaction.objects.filter(wallet=bw, transaction_type="USAGE_DEDUCTION").count() == 1
```

- [ ] **Step 2 — Run** → FAIL (today it would try to debit a seat wallet / mis-route).

- [ ] **Step 3 — Implement.** In `apps/billing/handlers.py` `handle_usage_recorded_billing`, change the `if billed_cost_micros > 0:` block to load the seat, resolve the owner for the money block, suspend/BalanceLow on the **owner**, and keep `record_usage_spend` on the **seat**:
```python
    if billed_cost_micros > 0:
        from apps.platform.customers.models import Customer
        seat = Customer.objects.get(id=payload["customer_id"])
        if tenant.billing_mode == "postpaid":
            pass  # no prepaid balance to draw down
        else:
            from apps.billing.wallets.models import WalletTransaction
            from apps.billing.locking import lock_for_billing
            from apps.billing.topups.models import AutoTopUpConfig
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import BalanceLow, CustomerSuspended
            from apps.billing.accounts import resolve_billing_owner_id

            owner_id = resolve_billing_owner_id(seat)
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                wallet.balance_micros -= billed_cost_micros
                wallet.save(update_fields=["balance_micros", "updated_at"])
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="USAGE_DEDUCTION",
                    amount_micros=-billed_cost_micros, balance_after_micros=wallet.balance_micros,
                    description=f"Usage: {payload.get('event_id', '')}",
                    reference_id=payload.get("event_id", ""),
                    idempotency_key=f"usage_deduction:{event_id}")
                from apps.billing.queries import get_customer_min_balance
                threshold = get_customer_min_balance(owner.id, tenant.id)
                if wallet.balance_micros < -threshold and owner.status == "active":
                    owner.status = "suspended"
                    owner.save(update_fields=["status", "updated_at"])
                    write_event(CustomerSuspended(
                        tenant_id=str(tenant.id), customer_id=str(owner.id),
                        reason="min_balance_exceeded", balance_micros=wallet.balance_micros))
                try:
                    config = AutoTopUpConfig.objects.get(customer=owner, is_enabled=True)
                except AutoTopUpConfig.DoesNotExist:
                    config = None
                if config and wallet.balance_micros < config.trigger_threshold_micros:
                    write_event(BalanceLow(
                        tenant_id=str(tenant.id), customer_id=str(owner.id),
                        balance_micros=wallet.balance_micros,
                        threshold_micros=config.trigger_threshold_micros,
                        suggested_topup_micros=config.top_up_amount_micros))

        # Shared tail — control + attribution stay on the SEAT:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
        from apps.billing.gating.services.budget_service import BudgetService
        BudgetService.record_usage_spend(seat, billed_cost_micros)
```
> Because `BalanceLow.customer_id` is now the **owner** (business) for a pooled seat, the Stage-C connector (`handle_balance_low_stripe`) creates the top-up attempt on the business and `apply_topup_credit` credits the business wallet — no Stage-C change needed.

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/tests/test_outbox_handlers.py -q` → green (existing individual/postpaid tests + the new pooled-seat test). **Commit:** `feat(accounts): drawdown routes pooled-seat money to the business, spend to the seat`.

---

### Task 3: Gate — affordability/status→owner, budget/rate→seat

**Files:** Modify `apps/billing/gating/services/risk_service.py`; Test `apps/billing/gating/tests/test_risk_service.py` (append to `TestRiskServiceBudget`).

- [ ] **Step 1 — Failing tests** (append):
```python
    def test_suspended_business_gates_its_seat(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled", status="suspended")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        res = RiskService.check(seat)
        assert res["allowed"] is False and res["reason"] == "insufficient_funds"

    def test_pooled_seat_affordability_reads_business_wallet(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=-9_999_999)  # business pool deep negative
        assert RiskService.check(seat)["allowed"] is False  # gated on the business pool
```

- [ ] **Step 2 — Run** → FAIL (gate reads the seat's own wallet/status today).

- [ ] **Step 3 — Implement.** Rewrite `RiskService.check` to resolve the owner for affordability + status while keeping rate-limit + budget on the seat:
```python
    @staticmethod
    def check(customer, create_run=False, run_metadata=None, external_run_id=""):
        from apps.billing.accounts import resolve_billing_owner
        owner = resolve_billing_owner(customer)
        # Status: gate if the seat OR its billing-owner (business) is suspended/closed
        for who in ([customer] if owner.id == customer.id else [customer, owner]):
            if who.status == "suspended":
                return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None, "run_id": None}
            if who.status == "closed":
                return {"allowed": False, "reason": "account_closed", "balance_micros": None, "run_id": None}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            config = None
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            try:
                cache_key = f"ratelimit:{customer.id}:rpm"  # per-SEAT
                current_count = cache.get(cache_key, 0)
                if current_count >= config.max_requests_per_minute:
                    return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None, "run_id": None}
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=60)
            except Exception:
                pass

        # Affordability: the OWNER's wallet + min-balance (the pool for a pooled seat)
        from apps.billing.wallets.models import Wallet
        try:
            balance = Wallet.objects.get(customer=owner).balance_micros
        except Wallet.DoesNotExist:
            balance = 0
        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(owner.id, owner.tenant_id)
        if owner.tenant.billing_mode != "postpaid" and balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance, "run_id": None}

        # Budget cap: per-SEAT
        from apps.billing.gating.services.budget_service import BudgetService
        budget = BudgetService.check(customer)
        if not budget["allowed"]:
            return {"allowed": False, "reason": budget["reason"], "balance_micros": balance, "run_id": None}

        result = {"allowed": True, "reason": None, "balance_micros": balance, "run_id": None}
        if create_run:
            from apps.billing.queries import get_billing_config
            from apps.platform.runs.services import RunService
            billing_config = get_billing_config(customer.tenant_id)
            run = RunService.create_run(
                tenant=customer.tenant, customer=customer, balance_snapshot_micros=balance,
                cost_limit_micros=billing_config.run_cost_limit_micros,
                hard_stop_balance_micros=billing_config.hard_stop_balance_micros,
                metadata=run_metadata or {}, external_run_id=external_run_id)
            result["run_id"] = str(run.id)
            result["cost_limit_micros"] = run.cost_limit_micros
            result["hard_stop_balance_micros"] = run.hard_stop_balance_micros
        return result
```
> Per-seat enforcing `BudgetConfig` still gates only the seat (via `BudgetService.check(customer)`) — the pool keeps funding the others.

- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/billing/gating -q` → green (existing gate tests for individuals unchanged + the 2 new). **Commit:** `feat(accounts): gate resolves affordability/status to the business, budget/rate to the seat`.

---

### Task 4: Orchestrator API — create business/seat + view business

**Files:** Modify `api/v1/platform_endpoints.py`; Test `api/v1/tests/test_accounts_api.py`.

- [ ] **Step 1 — Failing tests** `api/v1/tests/test_accounts_api.py`: with a Bearer key (mirror an existing platform endpoint test): POST `/api/v1/customers` `{"external_id":"biz","account_type":"business","billing_topology":"pooled"}` → 201; POST `{"external_id":"s1","account_type":"seat","parent_external_id":"biz"}` → 201 and the created seat's `parent` is the business; POST a seat with a missing `parent_external_id` → 422; GET `/api/v1/accounts/business/biz` → 200 with `seats` listing `s1` and a `pooled_balance_micros`. Also: a plain POST `{"external_id":"ind"}` still creates an `individual` (backward-compat).
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Schemas + endpoint** in `api/v1/platform_endpoints.py`: extend `CreateCustomerRequest` + add validation + a business view. Replace/extend:
```python
class CreateCustomerRequest(Schema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}
    account_type: str = "individual"          # individual | business | seat
    parent_external_id: str = ""              # required when account_type == "seat"
    billing_topology: str = ""                # required when account_type == "business"


@platform_api.post("/customers", response={201: CustomerResponse, 409: dict, 422: dict})
def create_customer(request, payload: CreateCustomerRequest):
    tenant = request.auth.tenant
    at = payload.account_type or "individual"
    if at not in ("individual", "business", "seat"):
        return 422, {"error": f"invalid account_type {at}"}
    parent = None
    topology = ""
    if at == "seat":
        if not payload.parent_external_id:
            return 422, {"error": "seat requires parent_external_id"}
        parent = Customer.objects.filter(tenant=tenant, external_id=payload.parent_external_id,
                                         account_type="business").first()
        if parent is None:
            return 422, {"error": "parent business not found"}
    elif at == "business":
        if payload.billing_topology not in ("pooled", "allocated"):
            return 422, {"error": "business requires billing_topology pooled|allocated"}
        topology = payload.billing_topology
    try:
        customer = Customer.objects.create(
            tenant=tenant, external_id=payload.external_id,
            stripe_customer_id=payload.stripe_customer_id, metadata=payload.metadata,
            account_type=at, parent=parent, billing_topology=topology)
        return 201, {"id": str(customer.id), "external_id": customer.external_id,
                     "stripe_customer_id": customer.stripe_customer_id, "status": customer.status}
    except IntegrityError:
        return 409, {"error": "Customer with this external_id already exists"}


@platform_api.get("/accounts/business/{external_id}", response={200: dict, 404: dict})
def get_business(request, external_id: str):
    from apps.billing.wallets.models import Wallet
    biz = Customer.objects.filter(tenant=request.auth.tenant, external_id=external_id,
                                  account_type="business").first()
    if biz is None:
        return 404, {"error": "business not found"}
    pooled_balance = None
    if biz.billing_topology == "pooled":
        w = Wallet.objects.filter(customer=biz).first()
        pooled_balance = w.balance_micros if w else 0
    seats = [{"external_id": s.external_id, "id": str(s.id), "status": s.status}
             for s in biz.seats.all().order_by("external_id")]
    return 200, {"external_id": biz.external_id, "id": str(biz.id),
                 "billing_topology": biz.billing_topology,
                 "pooled_balance_micros": pooled_balance, "seats": seats}
```
- [ ] **Step 4 — Verify:** `$DJ manage.py check`; `$DJ -m pytest api/v1/tests/test_accounts_api.py api/v1 -q` → green. **Commit:** `feat(accounts): create business/seat + business view API`.

---

### Task 5: SDK — account_type/parent on create + get_business

**Files:** Modify the SDK platform/customer client (find where `create_customer` lives — `git grep -n "def create_customer" ubb-sdk/`) + `ubb-sdk/ubb/types.py`; Test `ubb-sdk/tests/test_accounts_client.py`.

- [ ] **Step 1 — Implement.** Extend the SDK `create_customer` to accept `account_type="individual"`, `parent_external_id=""`, `billing_topology=""` and pass them in the JSON body (match the existing method's request helper + path `/api/v1/customers`). Add `get_business(external_id)` → GET `/api/v1/accounts/business/{external_id}` returning the parsed dict. Mirror the style of an existing SDK method.
- [ ] **Step 2 — Tests** `ubb-sdk/tests/test_accounts_client.py`: mock the httpx client; assert `create_customer(external_id="biz", account_type="business", billing_topology="pooled")` posts those fields to `/api/v1/customers`; assert `get_business("biz")` GETs `/api/v1/accounts/business/biz`. Mirror `tests/test_rate_card_client.py`.
- [ ] **Step 3 — Verify:** from `ubb-sdk/` (no `DJANGO_SETTINGS_MODULE`): `<venv python> -m pytest -q` → green. **Commit (repo root):** `feat(sdk): account_type/parent on create_customer + get_business`.

---

### Task 6: Backward-compat + final verification

- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB (REQUIRED):** drop/recreate `ubb`; `$DJ manage.py migrate` applies `customers/0011` cleanly; `$DJ -m pytest -q` whole platform suite green; `cd ../ubb-sdk && <venv python> -m pytest -q` green.
- [ ] **Backward-compat assertion:** the full suite passing IS the backward-compat proof — every pre-existing individual-customer drawdown/gate/auto-top-up test runs unchanged because `resolve_billing_owner` returns self for non-pooled-seats.
- [ ] **E1 e2e spot-check:** a pooled business (`get_business` shows the pooled balance) + 2 seats; each seat's usage debits the **business** wallet and records spend on the **seat**; the pool dipping below the business auto-top-up threshold emits `BalanceLow` on the **business** (→ Stage-C tops up the business); suspending the business gates both seats; an allocated business's seats each behave as a flat customer.

---

## Self-Review

**Spec coverage (E1 scope):** hierarchy fields + validation (T1/T4) ✓; `resolve_billing_owner` (T1) ✓; drawdown money→owner / control→seat (T2) ✓; auto-top-up follows via `BalanceLow.customer_id`=owner (T2 note) ✓; gate affordability/status→owner, budget/rate→seat (T3) ✓; per-seat caps reuse `BudgetConfig` (T3, no new code) ✓; suspension semantics (T2 suspend owner + T3 gate-on-owner-status) ✓; orchestrator API create business/seat + view (T4) ✓; SDK (T5) ✓; backward-compat for individuals (T6) ✓. *(Margin rollup + postpaid consolidated invoice = E2, separate plan.)*

**Placeholder scan:** T5 says "find where create_customer lives" with the exact `git grep` + path; T4 tests say "mirror an existing platform endpoint test" with concrete asserts. No TBD/TODO.

**Type/name consistency:** `resolve_billing_owner(customer) -> Customer` / `resolve_billing_owner_id(customer) -> uuid` defined T1, used T2 (`resolve_billing_owner_id`) + T3 (`resolve_billing_owner`). `account_type`/`parent`/`billing_topology` fields defined T1, used T2/T3/T4. `BalanceLow.customer_id`=owner (T2) is what makes Stage-C target the business. Drawdown keeps `seat` for `record_usage_spend`; gate keeps `customer` for budget/rate.

**Migration risk:** one additive migration (`customers/0011`), DB-validated T1 + fresh-DB T6.
