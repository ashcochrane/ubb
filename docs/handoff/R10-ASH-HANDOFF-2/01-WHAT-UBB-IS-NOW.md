PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# 01 - What UBB is now (at `a6738e78e96ab10eabd45dc10fafdc842b7de519`, 2026-11-09)

Plain English, for someone who has not read the code. Every sentence rests on the code at the anchor, its tests, or
the Stage D local run (`R10-BILLING-STAGE-D-EVIDENCE/`); where it rests on a ruling or a plan instead, it says so. The
citations are in `02-TECHNICAL-SYSTEM-MAP.md`.

## In one paragraph

UBB is a usage-metering, pricing, spend-control and margin service that sits between an AI application and Stripe.
A tenant (the client business) declares what it meters, what its suppliers charge, what it charges its own customers,
and the limits it wants enforced; its software then sends one HTTP call per usage event and UBB prices it, records an
immutable economic posting with a pricing receipt, rolls it into the unit of work it belongs to, decides on the spot
whether anything must stop, and answers with the cost, the price and the stop verdict. Stripe stays the billing
*engine* (invoices, collection, tax, dunning, refunds, disputes); UBB is the control plane that decides what to bill
and keeps the economic truth. UBB has four **product domains** in the codebase - metering, billing, subscriptions
and referrals - which sit on a shared platform kernel and talk only through four named channels (outbox events,
`queries.py` read contracts, `ports.py`, platform hooks), enforced by a CI test. **Tenant product flags are not
one-for-one with those domains.** `Tenant.products` admits exactly three values at the anchor - `metering` (always
present), `billing` and `referrals` (`domain-vocabulary/concepts/economics.yaml`, `apps/platform/tenants/models.py`).
`subscriptions` is **not** a tenant product flag and never was one that survives today: plans and the subscription
lifecycle are gated through `billing`; referrals is gated through `referrals`. (D2, PR #632, removes the retired
`subscriptions` flag from the SDK README's journey for exactly this reason.) The first external client uses the
`external` billing mode, in which UBB meters and reports and moves no money at all.

## The three billing modes

- **`external`** (the default and the first launch): UBB meters, prices, controls and reports; it holds no wallet,
  pushes no invoice, touches no rail. A tenant may also enable the `billing` product in this mode - it gets plans,
  spend pools, the platform-fee period and postpaid configuration, but every wallet operation, mutating or read-only,
  answers `403 feature_not_enabled` ("wallet operations are not available in this tenant's billing mode") and
  affordability answers with null balances, never zero.
- **`prepaid`**: each customer's billing owner holds a wallet in integer micros of US dollars. Money comes in by an
  operator credit, a paid or promotional credit grant (grants expire and are consumed first), or a Stripe top-up
  (Checkout on the tenant's connected account, or an automatic top-up when the balance falls under a threshold).
  Every priced usage event draws the wallet down exactly once, keyed on the event. Floors: a soft floor refuses new
  top-level work; a hard floor suspends the customer. Under `enforcement_mode=off` the suspension is a durable status
  the credit hook and the hourly pass lift from the wallet's truth; under `enforcing` a Redis live counter and a
  stop-signal ledger stop work in real time and the same recovery clears the stop. Refunds, withdrawals, reservations
  for fixed-price work, Stripe refund claw-backs and dispute claw-backs are all ledger lines on the same wallet.
- **`postpaid`**: no wallet. Each billing owner's month of priced usage is pushed to Stripe as one invoice with line
  items (or ridden onto the renewal invoice of an active subscription), with sub-cent residue carried forward exactly
  once; the push is resumable, idempotency-keyed, bounded by attempt and age caps, and repushable by an operator.
  Stripe's `invoice.paid` / `payment_failed` / `voided` events keep the invoice's payment status; a failed payment
  suspends the invoice's historical billing owner (`payment_failed`) and the last settlement reactivates it. UBB's own
  platform fee to the tenant is a separate Stripe invoice on UBB's account.

A money mode needs an enabled **payment-rail activation** (an operator-approved row per environment, held by a
database trigger as well as the model); its flag closes new money everywhere at once. The first client is admitted
without one.

## The payment rail and the Stripe boundary

Every outbound Stripe call goes through one wrapper (`stripe_call`) that refuses to run without the tenant's mode key
(so a deployment with no key makes no request), injects the idempotency key, retries connection errors with backoff
and maps Stripe's errors to UBB's named ones; a CI AST guard refuses any raw SDK call outside it, and a second guard
refuses dict-style reads of Stripe objects (the pinned `stripe==15.2.0` objects are attribute objects). Inbound, two
webhook receivers - billing (`/api/v1/webhooks/stripe`) and subscriptions (`/api/v1/subscriptions/webhooks/stripe`) -
each verify with their own signing secret, fail closed on a blank one, and deduplicate per receiver, so one Stripe
event delivered to both is handled once by its owner and never buried by the other's row. A failed retryable event
can be re-run by an operator command on its own record.

## What changed through Stage A-C5 (2026-11-02 → 2026-11-09)

Stage B's verification pass on the Stage A anchor found 5 billing blockers, 12 required fixes and 4 adjacent findings
(`R10-BILLING-READINESS/findings.md`). Six merged slices repaired every one of them; Stage D re-proved each on the
final tree:

- **Stage A (#625)** - the wallet-subject perimeter: every wallet-mutating route refuses a mode that holds no wallet.
- **C1a (#626)** - Stripe object and transport integrity: production reads the real stripe-python object model;
  every outbound call is behind the wrapper (F-2, F-3a, F-3b, O-1).
- **C1b (#627)** - the receiver core shared by both receivers with per-receiver dedup and the subscriptions receiver's
  own secret (F-17); a top-up refuses before it writes, each refusal by its truthful problem (F-11, O-6); Stripe
  refunds claw back exactly the increment of the cumulative refunded amount, duplicates never twice, and a refund
  Stripe later fails is an alert, never an automatic re-credit (Q15, Q19, Q20).
- **C2 (#628)** - `customer.reactivated`, emitted exactly once on the real suspended → active transition; the
  `off`-mode hard-floor suspension clears from durable wallet truth (F-1); a payment failure suspends the invoice's
  frozen historical billing owner with `payment_failed`, and only the last settlement reactivates (F-6); the frozen
  `SubscriptionInvoice.billing_owner`.
- **C3 (#629)** - an allocated seat's usage closes on the seat (F-7); the postpaid claim is committed before anything
  can throw, so a failed close is retried (F-8); a sub-cent month is `skipped`/`below_minor_unit` with its carry
  moved once, never `pushed` (F-9); `set_platform_billing_customer` is the operator path for UBB's platform-fee
  customer (F-10).
- **C4 (#630)** - a subscribe is one outcome: no plan assignment, no audit row and no mirror without the subscription
  (A-1); a seat roster change pushes the Stripe quantity and an hourly reconciler converges any missed push under a
  deterministic per-episode key (A-2, item 40); mirror identity binds once and never rebinds, ambiguity binds nowhere
  (items 30/33-38); an invoice arriving before its mirror is retried and recoverable by `reprocess_webhook --tenant`
  (item 36); the manual hold is one operator command over one service (item 41); a payment recovery hands over to a
  standing money cause instead of activating a customer still past its floor (item 43).
- **C5 (#631)** - the one breaking regeneration of the pre-live lane and SDK 5.0.0: a typed 202 on both top-up
  routes (F-5); the read-only wallet surfaces refuse where the mode holds no wallet (F-12); credit/debit take the
  platform customer UUID only (F-13); one durable refund id (F-14); one shared usage-invoice shape across the three
  routes with a closed nullable `payment_status` (F-15); the SDK's auto-top-up parameters required (F-4) and the
  tenant-config control fields sendable (O-5); referral rewards in explicit units - micros or basis points - with a
  flat fee paid once per referral (A-3); the RS256 backend pinned in the lock and proven in a clean environment (F-16);
  the durable manual-hold audit actions (item 42).

## The four product domains in one line each

- **Metering**: Event Types, cost books, pricing books, receipts, postings, charges, economics - the kernel's truth.
- **Billing**: wallets and their ledger, floors and stops, top-ups, postpaid usage invoices, the platform fee, the
  Stripe connector, the two receivers, the manual hold.
- **Subscriptions**: the plan catalogue realised as Stripe Prices, subscribe/seats/lifecycle/re-price, the mirror,
  subscription invoices, the seat-quantity reconciler.
- **Referrals**: programs (flat fee in micros, or a share in basis points), referrers and codes, attribution, the
  reward accumulator and the per-period ledger, payout export.

## How a client integrates (unchanged shape)

An operator creates the tenant and mints the first key (`TenantApiKey.create_key`; shown once). The client calls
`/api/v1` with `Authorization: Bearer ubb_live_…` (a `ubb_test_` key routes to the sandbox sibling), creates its
customers, declares and publishes Event Types and prices, then records usage - directly or through **SDK 5.0.0**
(`ubb-sdk`, hand-written wrappers over a generated core stamped with the spec's SHA-256; released 2026-11-09 as the
annotated tag `sdk-v5.0.0` on `b41b395f…` with the reproducibly built wheel `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256
`56d28b90…`, handed over in `R10-SDK-V5-RELEASE/`; not published to PyPI) - or through the **Code Builder**, which renders a tenant's selection into a Python module
(SDK major 5) or a shell file. End customers read their own balance, grants, transactions, invoices and economics
with a short-lived widget token.

## What is deliberately NOT part of the first external-client launch

- Any money movement: the first tenant is `external` and does not enter prepaid or postpaid money movement - no
  wallet, no top-up, no postpaid push. These are built and proven locally; a money mode additionally requires the
  `billing` product and an enabled payment-rail activation, neither of which the first client has.
- Fee-bearing, Stripe-backed plan and subscription operations (Stripe Prices, subscribe, seats, subscription
  invoices): built and proven locally; they require the `billing` product and the relevant Stripe / rail readiness
  (`05`). They do not carry their own tenant product flag - no retired `subscriptions` flag exists.
- Referrals: built and proven locally; it is separately product-gated (`referrals`) and is simply not enabled for the
  first client. It does not itself require a payment rail.
- A real payment rail: no `PaymentRailActivation` exists outside disposable test databases; activation is an
  accountable human act (`05`).
- Stripe test-mode integration, Connect onboarding, public HTTPS webhook receipt, the production image, the SLOs, the
  Clerk production environment: all inherited (`05`). The `sdk-v5.0.0` release act is COMPLETE (2026-11-09; `05` §9,
  `R10-SDK-V5-RELEASE/`) and is not inherited.
- Automatic reversal of a Stripe refund that later fails; closing a customer; rebinding a subscription mirror;
  a Customer list/search API; FX or any currency but USD; a TypeScript SDK.
