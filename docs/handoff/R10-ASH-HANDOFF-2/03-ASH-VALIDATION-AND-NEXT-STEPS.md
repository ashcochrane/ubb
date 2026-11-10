PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# 03 - Validation procedure and next steps for Ash

Anchored to `a6738e78e96ab10eabd45dc10fafdc842b7de519` (the D1 behavioral proof anchor). Every command below is
either **safe local verification** (a laptop, local containers, a disposable database; nothing outside the machine)
or **production-only / do not run yet**. Nothing here is admission or rail-activation evidence. The original recipe
(`R10-ASH-HANDOFF/03`) still holds for the metering golden path; this file adds the billing golden paths Stage D ran
and what changed since.

## Where the programme is now

- The D1 behavioural proof anchor is `a6738e78…` (at D1, `main` was `a6738e78…`): the reviewed C5 tree, Stage A + C1a-C5 merged through the temporary R10 merge guard
  (PLAN §9). Stage D re-proved every golden path on it with zero BILLING BLOCKER / PRE-ASH REQUIRED FIX.
- The one D2 docs-only PR (#632: the SDK README install line and retired flag, the codegen README major/catalogue,
  the billing and platform glossaries) was guard-merged on 2026-11-09 → `main` = `b41b395f59d798cec83289d83d5ec71f83201c7f`,
  sole parent `a6738e78…`, tree identical to the reviewed head. It changes no behaviour; every proof here stands on
  it unchanged (`00-README.md`, D2 MERGED).
- `sdk-v5.0.0` IS tagged and its wheel IS built (the owner's separately authorised release act, 2026-11-09): an
  annotated tag on the post-D2 `main` `b41b395f…`; wheel `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90…`, with its
  release manifest and verification in `R10-SDK-V5-RELEASE/`; not published to PyPI. The repository declares 5.0.0
  (`ubb-sdk/pyproject.toml`, `ubb.__version__`, `MIGRATION.md §27`, `CHANGELOG.md`).
- The docs-only SDK release-record PR #633 (`ubb-sdk/CHANGELOG.md`, the released wheel's SHA-256) was guard-merged on
  2026-11-09 → `main` = `90d008b709a86ff0d63588d8dd6b0a160978230b`, sole parent `b41b395f…`. **Current `main` is therefore
  `90d008b7…`**: two documentation-only commits past the D1 proof anchor `a6738e78…`, with no billing behaviour changed.
- W7 remains `PRE-LAUNCH - NOT FINAL`. Its starting baseline was refreshed on 2026-11-09 (the final transition window) to
  `90d008b709a86ff0d63588d8dd6b0a160978230b` - a pointer refresh only; W7 has not been executed.
- Nothing has ever been deployed; no real tenant is admitted; `docs/api-compatibility.md:10` still carries "no tenant
  is live on v1 yet".

## 0. Prerequisites (safe local verification)

Docker (PostgreSQL 16, Redis 7), Python 3.13, Node 22-24 and pnpm 10.28 (console/codegen only), Git Bash on Windows.
Use a clean clone at the anchor and a **dedicated database name** (a database migrated before the W6 squash cannot
migrate forward). Put no real Stripe or Clerk value anywhere; none is needed below.

```sh
git clone <repo> ubb && cd ubb && git checkout a6738e78e96ab10eabd45dc10fafdc842b7de519
docker compose up -d                                   # postgres:16 (5433) and redis:7 (6380) per the compose file
cd ubb-platform && python -I -s -m venv .venv && . .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.lock.txt                   # pins cryptography/cffi/pycparser since C5 (F-16)
export PYTHONPATH=$PWD/../ubb-sdk                      # the SDK from the tree (or pip install the released wheel, R10-SDK-V5-RELEASE/)
docker exec ubb-postgres psql -U ubb -d postgres -c "CREATE DATABASE ubb_ash2"
export DATABASE_URL=postgres://ubb:<the local container password>@localhost:5433/ubb_ash2
export REDIS_URL=redis://localhost:6380/5 UBB_TEST_REDIS_DB=9 SECRET_KEY=local-throwaway DEBUG=True
export STRIPE_WEBHOOK_SECRET=whsec_localpass_a STRIPE_TEST_WEBHOOK_SECRET=whsec_localpass_b STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=whsec_localpass_c
unset STRIPE_SECRET_KEY                                # Level 1A: the wrapper refuses every outbound call
```

## 1. Static checks (expected results at the anchor; `R10-BILLING-STAGE-D-EVIDENCE/00-static.txt`)

```sh
python manage.py check                          # no issues
python manage.py migrate                        # 49 migrations on an empty database
python manage.py migrate                        # No migrations to apply
python manage.py makemigrations --check --dry-run   # No changes detected
python scripts/export_openapi.py && git -C .. status --short -- openapi/    # empty = byte-identical
cd .. && python openapi/contract_gate.py --baseline origin/main             # 0 breaking changes
python ubb-sdk/codegen/generate_core.py && python -m tools.sdk_operations --write && git status --short   # empty
python -m tools.gates && python -m tools.forbidden_terms && python -m tools.vocabulary --write           # 27/27, 0, up to date
```

## 2. The stack

```sh
cd ubb-platform
python manage.py runserver 127.0.0.1:8017 --noreload
celery -A config worker --pool=solo -l INFO          # nine ubb_* queues
celery -A config beat -l INFO --schedule /tmp/celerybeat-schedule
curl -s http://127.0.0.1:8017/api/v1/ready           # {"status":"ready","checks":{"database":"ok","redis":"ok"}}
```

Stop all three before any pytest (the beat-schedule test rings a doorbell a live worker would consume).

## 3. The rail fixture (only in a disposable database)

A money mode needs an enabled activation. In `python manage.py shell` on the disposable database:

```python
from django.utils import timezone
from apps.platform.tenants.models import PaymentRailActivation
PaymentRailActivation.objects.create(rail="stripe", environment="live", enabled=True, activated_at=timezone.now(),
    approved_by="local test fixture - no human approval",
    evidence="LOCAL/TEST RAIL FIXTURE - NOT PAYMENT-RAIL ACTIVATION EVIDENCE - <date>")
```

It activates nothing anywhere else; drop the database afterwards. Without it `PATCH /tenant/config
{"billing_mode":"prepaid"}` answers `409 payment_rail_not_activated` and `seed_dev_data --billing-mode postpaid` is
refused (TEST VERIFIED: `api/v1/tests/test_a_money_mode_needs_its_payment_rail.py`).

## 4. The smallest credible prepaid golden path (what `probes/p4_prepaid.py` does, by hand)

Create a tenant and key in a shell (`Tenant(name=…, products=["metering","billing"]).save()`;
`TenantApiKey.create_key(t, label=…)`), then with the key:

1. `PATCH /api/v1/tenant/config {"billing_mode":"prepaid","products":["metering","billing"],"enforcement_mode":"off","min_balance_micros":0}`
   (or SDK `UBBClient.update_tenant_config(..., enforcement_mode="off", min_balance_micros=0)`).
2. `POST /api/v1/platform/customers {"external_id":"c1"}` → keep the UUID `id`. No Wallet row exists yet.
3. `POST /api/v1/billing/credit {"customer_id":"<UUID>","amount_micros":20000000,"source":"manual","reference":"seed","idempotency_key":"credit-1"}`
   → the wallet is born, balance 20,000,000; replay the same key → the same `transaction_id`. The external id in that
   field → 422; a foreign UUID → 404.
4. Declare a supplier, a reported-cost Event Type and publish it; set a 20% default markup (as in the original recipe).
5. `POST /api/v1/metering/usage` with `provider_cost_micros 1000000` → ack `billed_cost_micros 1200000`, `stop false`;
   within seconds the worker writes ONE `usage_deduction` keyed `usage_deduction:{event_id}` and the balance reads
   18,800,000 on `GET /billing/customers/{id}/balance` and on `/me/balance` with a widget token.
6. Record a 20,000,000-cost event → the balance crosses the floor; the customer is `suspended`/`hard_floor`,
   `customer.suspended` is in the outbox, a `POST /tasks` answers `409 insufficient_funds`.
7. `POST /api/v1/billing/credit` 10,000,000 → the customer is `active` and EXACTLY ONE `customer.reactivated`
   (reason_code `hard_floor`) is in the outbox; no `StopSignalState`, no `customer.stopped`/`stop_cleared` under `off`.
8. `python manage.py set_customer_manual_hold --customer <UUID> --state held --operator you` → suspended with reason
   `""` and one `customer.manual_hold_set` audit row; `--state released` → active, one `customer.manual_hold_released`
   row (resulting `active`) and one `customer.reactivated`.
9. `POST /billing/customers/{id}/top-up` with no connector → `202 {"status":"topup_requested","message":…}` and one
   `top_up.requested`; the same key again → 202, no second event.
10. `POST /billing/customers/{id}/refund {"usage_event_id":…,"idempotency_key":"r1"}` → `refund_id` = the refund
    transaction id; replay → the SAME id; the credit's key as a refund key → 409 `conflict`.
11. Economics: `/metering/analytics/economics` and `/me/economics` customer revenue = the sum of the postings, unmoved
    by any wallet movement; the wallet balance = the ledger sum.

## 5. The smallest credible postpaid golden path (`probes/p5_postpaid.py`, by hand)

1. `PATCH /tenant/config {"billing_mode":"postpaid","products":["metering","billing"]}`; a customer with a caller-supplied
   placeholder `stripe_customer_id` (`cus_localpass_…`), one without.
2. Record priced usage; `GET /tenant/billing-periods` shows the accruing period; every wallet route (mutating and
   read-only) answers 403 `feature_not_enabled`.
3. In a shell, `PostpaidUsageService.push_customer_period(tenant, customer, period_start, period_end)` with NO connected
   account → `skipped not_charge_ready`; the customer without a Stripe id → `skipped no_stripe_customer`; nothing
   reaches the SDK.
4. A real push needs Stripe or Level 1B: patch `apps.billing.invoicing.services.postpaid_service.stripe.Invoice.create
   / retrieve / list`, `InvoiceItem.create / list`, `Invoice.finalize_invoice` with REAL `stripe.Invoice.construct_from(...)`
   objects, install the transport block (`stripe._api_requestor._APIRequestor.request_raw` → a raiser, the
   `conftest._stripe_guard` shape), override the key in process with the published sentinel, set the placeholder
   connected account + `charges_enabled` inside that block only, then push: ONE `Invoice.create` keyed
   `usage-invoice-{row.id}`, N items `usage-item-{row.id}-{i}`, one finalize; the row `pushed` with the invoice id;
   `usage_invoice.pushed` once; all three usage-invoice routes show the same shared shape with `payment_status null`.
5. Deliver a locally signed `invoice.payment_failed` (event `account` = the placeholder) → `payment_failed_at` set and the
   customer `suspended`/`payment_failed`; `invoice.paid` → `payment_status paid`, the customer `active`, ONE
   `customer.reactivated` (reason_code `payment_failed`).
6. Close the current fee period by hand (`TenantBillingService.close_period`) → `platform_fee_micros` and a
   `PlatformFeeCarry`; `generate_tenant_platform_invoices` with no platform customer leaves it `closed` and logs
   `platform_invoice.no_platform_customer`; `python manage.py set_platform_billing_customer --tenant <id>
   --stripe-customer-id cus_… --operator you` then (Level 1B) one platform-fee `Invoice.create` keyed
   `platform-invoice-{period.id}`.

## 6. The suites (safe; one pytest at a time; stop the stack first)

```sh
cd ubb-platform                                              # DJANGO_SETTINGS_MODULE=config.settings
python -m pytest api/v1/tests                                # 2,495 passed
python -m pytest apps/platform core                          # 1,760 passed
python -m pytest apps/billing                                # 938 passed, 3 skipped (opt-in live Stripe)
python -m pytest apps/subscriptions                          # 242 passed
python -m pytest apps/metering apps/referrals                # 1,349 passed
cd .. && unset DJANGO_SETTINGS_MODULE && python -m pytest tests/contracts     # 848 passed
cd ubb-sdk && unset PYTHONPATH && python -m pytest           # 477 passed
cd .. && python -m pytest tests/code_builder_execution       # 80 passed (Docker)
pnpm install --frozen-lockfile && pnpm --dir apps/ui typecheck && pnpm --dir apps/ui test && pnpm --dir apps/ui build
pnpm --dir apps/codegen typecheck && pnpm --dir apps/codegen lint && pnpm --dir apps/codegen test   # Windows: UBB_CODEGEN_SHELL_IMAGE=ubb-codegen-shell
```

Stage D ran exactly these (partitioned where a tree exceeds a 10-minute foreground cap, union proven) and got
8,192 collected = 8,189 passed + 3 skipped; console 1,342 vitest passed; codegen 902 passed. On Windows run
`apps/ui`'s API sync under Git Bash (`API_SPEC_PATH=../../openapi/v1.json bash scripts/generate-api.sh regen`).

## 7. The isolated F-16 proof (why production Clerk auth now works from the lock)

In a `python -I -s -m venv` with user-site disabled: `pip install -r requirements.lock.txt` installs
`cryptography==50.0.2`, then `python -m pytest core/tests/test_clerk_auth.py` → 15 passed (the RS256 PEM and JWKS
tests included); uninstall `cryptography` there → those 7 ERROR; reinstall → 15 passed
(`R10-BILLING-STAGE-D-EVIDENCE/13-f16-clean-env-proof.txt`).

## 8. What cannot faithfully be demonstrated locally

- **Stripe test mode** (R-1): a real test-mode push, checkout, PaymentIntent, `invoice.paid` at
  `/api/v1/webhooks/stripe/test` through a public receiver, `test_live_stripe_ar.py` (opt-in: `UBB_STRIPE_LIVE_TEST=1`
  + `STRIPE_TEST_SECRET_KEY` + `STRIPE_TEST_CONNECTED_ACCOUNT`; plus `STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET` and
  `STRIPE_CONNECT_TEST_CLIENT_ID` for the subscriptions receiver and Connect). Every Stage D proof stops at the wrapper
  or at a real constructed object with transport blocked.
- **Rail activation, Connect onboarding (`charges_enabled`), public-HTTPS webhook receipt and timing, the production
  image, HTTPS/proxy behaviour under `DEBUG=False`, SLO 1-3** (R-2).
- **The all-test Stripe layout question** (R-3): `livemode_filter` makes `invoice.*`/`account.*` handlers no-ops for
  non-sandbox tenants under test-mode events.
- **Real-browser console `api` mode**: needs a Clerk development environment (`VITE_CLERK_PUBLISHABLE_KEY`,
  `CLERK_JWKS_URL` or `CLERK_JWT_PUBLIC_KEY`). F-16 is repaired, so this is the Clerk environment alone. Mock-mode
  rendering is never proof that billing works.
- **A refund Stripe later fails or cancels** is alert-only by ruling (Q19): the operator path is to verify the Refund in
  Stripe and, if a re-credit is warranted, `POST /billing/credit` with a movement reason.

## Production-only / do not run yet

The W7 steps (`R10-W7-DELIVERY-PROMPT.md`): the deployment-files PR, the exact release record and image digest, the
production environment, SLO 1 first, the acceptance audit, the first real tenant on the release image, the admission
record. Also: any `PaymentRailActivation` outside a disposable database; `set_platform_billing_customer --verify`
against a real key. (`sdk-v5.0.0` and its wheel are DONE, 2026-11-09 - `R10-SDK-V5-RELEASE/`; the W7 anchor refresh to
`90d008b7…` is DONE, 2026-11-09, pointer only - W7 itself is still not to be run until its STATUS reads FINAL.)
