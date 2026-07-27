# Billing surface correctness — implementation plan

**Date:** 2026-07-27 · **Branch:** `feat/billing-surface-correctness` (off `main` @ `45c4b18`)
**Origin:** audit of the four spend controls (monthly budget, billing profile, task/subtask limits,
RiskConfig) and the surfaces that expose them.

Pre-live: no tenant depends on these contracts, so every change here is a clean cut — no aliases,
no dual-read windows, no deprecation shims.

## Why

The backend's mode split is sharp — `apps/billing/gating/crossing.py` owns both orientations and
`LiveCounter._threshold` picks exactly one line per `billing_mode` (postpaid → budget cap;
prepaid/meter_only → wallet floor). The defects are all at the edges:

1. **Pooled seats disagree with themselves.** `GET /balance` and `GET /transactions` read the
   *seat's* wallet; grants and `RiskService` read the *owner's*. A pooled seat shows `$0.00`
   and an empty ledger next to the business's real credit grants, and floors saved on the seat
   are never read by the gate.
2. **`billing_mode` barely reaches the UI.** The customer Billing tab has zero mode awareness, so
   postpaid tenants get a permanently-zero balance meter, top-up/withdraw buttons, grants,
   auto-top-up, and two floor fields that no code path reads.
3. **`Task.floor_snapshot_micros` is an independent third floor** that ignores the customer's real
   floor and can fire on a customer who just topped up.
4. **`BudgetConfig.enforce_mode` values collide** with the retired `Tenant.enforcement_mode`
   vocabulary and over-promise on prepaid.

## Decisions locked before implementation

- **The budget's prepaid behavior is CORRECT and does not change.** On prepaid the tenant has
  already collected the money and carries no credit risk, so the budget refuses *new task starts*
  and never interrupts running work; the wallet floor is the real wall and it is self-correcting
  (top up, keep going). On postpaid the tenant *is* extending credit, so the budget is the live
  stop line. Only the labels and copy change.
- **The two month-to-date counters stay.** `ubb:budget:{seat}:{month}` and
  `ubb:livespend:{owner}:{month}` are different aggregates with different merge semantics, not one
  value stored twice. Collapsing them when `owner == seat` would make the key identity conditional
  — a seat adopted into a business mid-month would silently split its counter with no migration
  path. What gets fixed is the undocumented *config-resolution* asymmetry (start gate resolves
  `BudgetConfig` seat-first; the postpaid crossing resolves owner-first): it is documented as an
  intentional two-level model and pinned by a test.
- **`Task.floor_snapshot_micros` is deleted, not repaired.** A defence-in-depth check may be more
  conservative than the authoritative one but must never be *independent* of it. This one reads a
  tenant-wide constant, never `CustomerBillingProfile.min_balance_micros`, and compares against a
  balance frozen at task start — so a mid-task top-up is invisible to it and it can kill a task
  belonging to a customer who just paid. It is also inert today
  (`default_task_floor_snapshot_micros` defaults NULL, so `crossed_floor_snapshot` has never
  evaluated true). The durable drawdown lane already detects the real floor crossing and fires
  `customer_wide_stop`, which is the correct scope for a wallet-wide fact.
- **Pooled seats: GET resolves, PUT refuses.** Reads (`/balance`, `/transactions`,
  `/billing-profile`) resolve the billing owner and say whose wallet they are showing. Writes
  (`PUT /billing-profile`) 422 with a message naming the owner — silently redirecting a write to
  the business would change every sibling seat's config while the operator believes they edited one
  seat.

## Global Constraints

Every task must honour these. Reviewers: treat a violation as an Important finding.

- **Product boundaries (ADR-001).** Products (`metering`, `billing`, `subscriptions`, `referrals`)
  communicate only via outbox events, `queries.py` read contracts, `ports.py`, and platform hooks.
  `apps/platform/tests/test_product_boundaries.py` is the gate and must stay green. The composition
  layer (`api/v1`, `apps/*/api`) may import any product; products never import `api.*`.
- **Local environment — export in EVERY shell; never edit `.env`.** `.env`'s `DATABASE_URL` points
  at a docker Postgres on `:5433` whose auth fails (that port is another project's container).
  The working database is the native one on `:5432`:
  ```bash
  export DATABASE_URL="postgresql://heyotis:heyotis@localhost:5432/ubb"
  export DJANGO_SETTINGS_MODULE=config.settings
  ```
- **Python is always the main checkout's venv, by absolute path:**
  `/Users/ashtoncochrane/Git/localscouta/ubb/ubb-platform/.venv/bin/python`. Never bare `python`.
- **Never run `manage.py migrate`.** The dev `ubb` database has a pre-existing, unrelated
  `InconsistentMigrationHistory` (`usage.0014_add_run_fk` recorded before its dependency
  `tasks.0001_initial`). `makemigrations` is fine; pytest builds a fresh test DB in dependency
  order and is the real check that a migration is sound.
- **First pytest invocation in a fresh worktree races on test-DB creation** and reports mass
  ERRORs. Re-run the same command once before believing a failure.
- **Regenerate the OpenAPI spec after ANY API surface change:**
  `.venv/bin/python scripts/export_openapi.py` refreshes the committed `openapi/v1.json` — the
  single source of truth for the tenant surface (ADR-002). CI has drift/breaking/TS gates.
- **Regenerate the UI's typed client** when `openapi/v1.json` changes, per `openapi/README.md` /
  the UI's generate script, so `apps/ui/src/api/generated/api.ts` matches.
- **Money is always micros**, integer, and currency codes are lowercase ISO (CUR-1).
- **Wire sign conventions are load-bearing.** `min_balance_micros` is the allowed-overdraft
  MAGNITUDE (≥ 0); the stop line is its negation. `soft_min_balance_micros` uses the same
  orientation (a negative wire value places the wind-down line above zero) and must resolve at or
  above the hard floor's line. Do not "fix" these to look natural.
- **Tests:** every behavioural change needs a test that fails without it. Do not weaken or delete
  an existing pin to make a change pass — if a pin genuinely encodes retired behaviour, say so in
  the report and delete it deliberately with the reason.
- **Commits:** conventional-commit subject lines, and every commit message ends with
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- **Scope discipline.** Do only the task in your brief. Note anything else you spot in your report
  rather than fixing it.

## Baseline

`apps/billing/invoicing` and `apps/subscriptions` carry pre-existing failures that predate this
branch. Record the baseline before you start and compare against it — do not chase failures your
task did not cause, and do not claim green without stating the baseline delta.

---

## Task 1 — Delete the per-task floor snapshot

**Goal:** remove the independent third floor entirely. After this task no code compares a task's
frozen balance snapshot against a floor, and no stop reason claims to be a customer floor.

**Delete:**

- `Task.floor_snapshot_micros` field (`apps/platform/tasks/models.py:67`) + migration. Note the
  model has a constraint referencing task fields at `models.py:120` — check whether it touches this
  column and amend it if so.
- **Keep** `Task.balance_snapshot_micros` — it stays as forensics on the task record even though
  its only current reader goes away. Say so in a comment on the field.
- `BillingTenantConfig.default_task_floor_snapshot_micros`
  (`apps/billing/tenant_billing/models.py:138`) + migration.
- The `crossed_floor_snapshot` verdict and its computation in `TaskService.accumulate_cost`
  (`apps/platform/tasks/services.py:141-149`), plus its mentions in that method's docstring.
- `CUSTOMER_FLOOR` from `apps/platform/tasks/reasons.py` — the constant, its membership in
  `ALL_REASONS` and `CROSSING_REASONS`, its branches in `kill_plan` and `stop_fields`, and the
  `kill_scope` docstring's reference to the floor snapshot.
- The `crossed_floor_snapshot` branch in `apps/metering/usage/services/stop_context.py:74`.
- `floor_snapshot_micros` from `PreCheckResponse` (`api/v1/schemas.py:50`) and from the
  `RiskService.check` result dict (`apps/billing/gating/services/risk_service.py:161,170`) —
  including the `TaskService.create_task` kwarg and its parameter
  (`apps/platform/tasks/services.py:16,41`).
- `default_task_floor_snapshot_micros` from the tenant config API: `api/v1/tenant_endpoints.py`
  (read at ~466, write at ~663-670) and `api/v1/schemas.py` (~812, ~844).
- The "Default task floor snapshot" field from
  `apps/ui/src/features/settings/components/spend-limits-form.tsx` (~106-108), its schema entry,
  its form default, and any assertion about it in the settings tests.
- `default_task_floor_snapshot_micros` from the UI's mock tenant config
  (`apps/ui/src/hooks/use-tenant-config.ts:33`) and any settings mock data.

**Keep untouched:** `RiskConfig.default_task_provider_cost_limit_micros` and
`default_subtask_provider_cost_limit_micros` — those are the COGS task limits, a different and
still-live control.

**Verify:** `grep -rn "floor_snapshot\|crossed_floor_snapshot\|CUSTOMER_FLOOR" ubb-platform/ apps/ui/src/`
returns only migration files. Run `apps/platform/tasks`, `apps/billing/gating`, `apps/metering`,
`api/v1` test packages plus the boundary test. Regenerate the OpenAPI spec and the UI client.

---

## Task 2 — Rename `BudgetConfig.enforce_mode` values and make the budget copy mode-aware

**Goal:** the budget's mode names say what they do, and stop colliding with the retired
`Tenant.enforcement_mode` vocabulary (`advisory` was mapped to `off` by tenants migration 0019).

**Rename** (clean cut, no aliases — pre-live):

- `advisory` → `alert_only` — emits threshold alerts, never refuses anything.
- `enforcing` → `blocking` — refuses new task starts; on postpaid *additionally* stops running work.

**Touch:**

- `BUDGET_ENFORCE_MODES` (`apps/billing/gating/models.py:31`) + a data migration rewriting existing
  rows (`advisory`→`alert_only`, `enforcing`→`blocking`) with a working reverse.
- `budget_stop_threshold` in `apps/billing/gating/crossing.py` — the `cfg.enforce_mode != "enforcing"`
  check and the module docstring's description of advisory semantics.
- `apps/billing/gating/services/budget_service.py` — any literal mode comparisons, and the
  `BudgetThresholdReached` event's `enforce_mode` payload field (value only; keep the field name).
- `api/v1/schemas.py` `BudgetConfigIn`/`BudgetConfigOut` and any validation of the literal set.
- UI: `budgetEnforceModeLabel` in `apps/ui/src/lib/labels.ts`, the select options and default in
  `apps/ui/src/features/customers/components/budget-section.tsx`, the equivalent in
  `apps/ui/src/features/billing/components/budget-card.tsx`, the zod schema in the customers
  feature's `lib/schemas.ts`, and the customers/billing mock data.

**Then add mode-aware copy.** Both budget surfaces must tell the operator what `blocking` actually
does for *their* `billing_mode` (read it from `useTenantConfig`):

- postpaid → blocking stops running work and fires a stop signal when month-to-date spend reaches
  the stop line.
- prepaid / meter_only → blocking refuses new task starts; work already running continues to
  completion, and the wallet floor is the control that interrupts it.

Keep the copy short and factual — one hint line under the mode select, not a paragraph.

**Verify:** grep for the old literals across `ubb-platform/` and `apps/ui/src/` (migrations aside).
Run `apps/billing/gating` and `api/v1` tests plus the UI test suite. Regenerate spec + UI client.

---

## Task 3 — Pooled seats: uniform billing-owner resolution

**Goal:** every billing read agrees about whose wallet funds a customer, and every billing write
either targets the right row or refuses honestly.

**Background:** `Customer.resolve_billing_owner()`
(`apps/platform/customers/models.py:51`) returns the parent business for a customer with
`account_type == "seat"` whose parent has `billing_topology == "pooled"`, else `self`.
`apps/billing/accounts.py` exposes `resolve_billing_owner` / `resolve_billing_owner_id`.

**Reads — resolve the owner and disclose it:**

- `GET /billing/customers/{id}/balance` (`api/v1/billing_endpoints.py:51`) — read the *owner's*
  wallet instead of the seat's.
- `GET /billing/customers/{id}/transactions` (`api/v1/billing_endpoints.py:295`) — same.
- `GET /billing/customers/{id}/billing-profile` (`api/v1/billing_endpoints.py:537`) — return the
  effective profile for the owner, matching what `get_customer_min_balance(owner.id, …)` resolves
  at the gate.

Add to the balance response schema (and thread the same disclosure through the other two where the
schema makes sense):

- `billing_owner_id` — the resolved owner's UUID (equals the customer's own id when not pooled)
- `billing_owner_external_id` — the owner's `external_id`, for display
- `is_pooled_seat` — boolean; true when the owner is a different customer

**Write — refuse honestly:**

- `PUT /billing/customers/{id}/billing-profile` (`api/v1/billing_endpoints.py:552`) — when the
  customer is a pooled seat, raise `Problem("invalid_config", …)` naming the billing owner's
  `external_id` and telling the caller to set floors on the business. Do NOT silently write to the
  owner's profile: that would change every sibling seat while the operator believes they edited one.

Use the existing `Problem` helper and the error vocabulary already in that module. Check whether
other customer-scoped billing writes in the same file (top-up, withdraw, credit, debit, auto-top-up)
already resolve the owner; if any do not, note it in your report — do not fix it in this task.

**Tests:** cover both topologies for each endpoint — an individual customer (owner == self,
`is_pooled_seat` false, behaviour unchanged) and a pooled seat (owner == business, balance and
transactions come from the business, PUT 422s). Include a non-pooled seat (parent exists but
`billing_topology != "pooled"`) to pin that it resolves to self.

**Verify:** `apps/billing` + `api/v1` tests, boundary test, spec + UI client regen.

---

## Task 4 — Mode-aware and topology-aware UI surfaces

**Goal:** the console only shows controls that do something for this tenant's `billing_mode`,
`enforcement_mode`, and this customer's billing topology. Depends on Tasks 1-3.

Follow the gating patterns already in the codebase — `ProductGate`
(`apps/ui/src/components/shared/product-gate.tsx`), `useTenantConfig` / `useHasProduct`
(`apps/ui/src/hooks/use-tenant-config.ts`), `useHasRole`, and the `billing_mode` branches in
`apps/ui/src/features/billing/components/billing-page.tsx:31` and
`apps/ui/src/features/dashboard/components/overview-page.tsx:33`.

**4a — customer Billing tab** (`apps/ui/src/features/customers/components/billing-tab.tsx`):

Under `billing_mode === "postpaid"`, the wallet is not the billing mechanism — drawdown skips
postpaid (`apps/billing/handlers.py:39`) and both floors are skipped at the gate
(`apps/billing/gating/services/risk_service.py:56,67`). So for postpaid:

- Hide: `GrantsSection`, the auto-top-up card, and the two floor fields of the billing-profile card.
- Keep: `BudgetSection` (the live control for postpaid), `TransactionsSection`,
  `UsageInvoicesSection`, and the Balance card with its manual credit/debit actions — manual
  adjustments still work for postpaid (`apps/billing/wallets/operations.py:218` skips only the floor
  check, not the debit).
- Hide the Top up / Withdraw buttons, which drive the prepaid credit flow.
- If the billing-profile card ends up with only `topup_grant_expiry_days` under postpaid, hide the
  whole card — top-up grants are prepaid-only too.

Explain the absence rather than silently dropping cards where a reader might look for them: a short
line on the tab saying this workspace bills postpaid and the wallet controls do not apply.

**4b — pooled-seat disclosure:** when the balance response reports `is_pooled_seat`, the Balance
card must say whose wallet it is showing and link to that customer. `past-limit-panel.tsx:137`
already has this pattern ("This customer draws a pooled wallet — episodes belong to billing
owner …") — match its phrasing and its link treatment. The billing-profile card must show the
floors as read-only in this case, with a line pointing at the business.

**4c — Settings spend limits** (`apps/ui/src/features/settings/components/spend-limits-form.tsx`):
the allowed-overdraft and wind-down-floor fields are wallet-based and inert under postpaid. Hide
them for postpaid with a one-line explanation, or disable them with the reason — match whichever
pattern `spend-control-card.tsx` already uses for unavailable controls.

**4d — enforcement disclosure:** the soft floor is `enforcing`-only
(`apps/billing/gating/services/risk_service.py:67`), so with `enforcement_mode === "off"` the
wind-down floor field does nothing and the past-limit report stays permanently empty. Add a hint on
the wind-down field and an explanatory empty state on `PastLimitSection` when enforcement is off.
`spend-control-card.tsx:114-115` already has accurate prose for both postures — reuse its wording
rather than inventing new phrasing.

**Tests:** the customers and settings feature test suites already render these components; extend
them to cover each mode branch. Keep to the existing test style in
`apps/ui/src/features/customers/components/customer-detail.test.tsx` and
`workspace-settings-page.test.tsx`.

---

## Task 5 — Document and pin the seat/owner budget scopes

**Goal:** the two-level budget resolution stops being folklore.

- **Pin it with a test** in `apps/billing/gating/tests/`: for a pooled business with seats, assert
  that `BudgetService.resolve_config_for(tenant, seat)` prefers the seat's own row while
  `LiveCounter._threshold("postpaid", owner, tenant)` resolves the owner's row (falling back to the
  tenant default when the business has none), and that the two counters
  (`ubb:budget:{seat}:{month}` vs `ubb:livespend:{owner}:{month}`) are independent. Use the `Door`
  test seam for counter state — `apps/billing/gating/services/live_counter.py` states that tests
  fabricate counter/flag state ONLY through `Door`, never by importing key helpers or the raw
  client.
- **Document it in `ubb-platform/apps/billing/CONTEXT.md`** as the ubiquitous-language entry for
  the budget: per-seat start caps plus an owner-aggregate stop line on postpaid, why the seat
  counter and the owner counter are different aggregates rather than duplicates, and the fact that
  a business customer's own budget row is what governs the aggregate.
- **Record the mode split** in the same file: on postpaid the budget is the live stop line; on
  prepaid/meter_only it is a start-gate control and the wallet floor is the wall. Include the
  reasoning (who carries the credit risk), because that is what makes the asymmetry legible.
- Note in `CONTEXT.md` that the per-task floor snapshot was removed in this branch and why, so the
  next reader does not reintroduce it.

Per the repo's ratchet rule, this is `CONTEXT.md` and test material — not a new dated plan doc.
Do not edit anything under `docs/plans/` or `docs/reviews/`: those are frozen history.
