# Progress Tracker — UBB Tenant Console

## Current Status

**2026-07-24 — Full rebuild on the regenerated v1 contract.** The console now covers the real
backend surface end to end: CFO overview, events ledger + pricing receipts + past-limit reports,
customer workbench (economics, usage, wallet/grants/budget, markup, price-book assignment,
subscription lifecycle), pricing books + atomic publish + markup, tenant billing operations,
subscriptions plans + Stripe sync, referrals (program/referrers/attribution/payouts), webhooks
(configs, deliveries, two-secret rotation), developers (return-once API keys, sandbox, test-event
console), and settings (workspace/spend control, team, products, UBB bill, audit log).

- Bootstrap: `GET /tenant/config` (billing_mode + products) gates nav and pages.
- Verified: tsc clean · eslint clean · 240+ vitest tests incl. a full route-tree smoke suite ·
  production build green.
- Known backend contract gaps are stated honestly in the UI (see the PR/report): no customer
  directory with external_id on margin list rows, no plans list, write-only auto-top-up and
  price-book assignment, resolved-only customer markup.

## History (pre-rebuild)

Phases 1–10 (2026-04) built the mock-first standalone app to HTML mockups: wizard, dashboard,
onboarding, mapping, reconciliation, margin management, export, v4 palette. That app's export and
reconciliation surfaces had no backend counterpart and were removed in the rebuild; their UX
patterns live on in `docs/design/` as reference. Git history preserves the code.
