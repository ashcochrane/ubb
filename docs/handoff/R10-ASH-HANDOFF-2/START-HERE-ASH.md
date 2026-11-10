PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# START HERE, ASH

Short and operational. This note is the entry point to `R10-ASH-HANDOFF-2/`, the authoritative engineering handoff for
UBB's billing readiness, rebuilt from the final verified system on 2026-11-09. It is not a system map; the map is `02`.

## A. Read in this order

1. `00-README.md` - the index, the three identities, the Stage D evidence record, the closing record.
2. `01-WHAT-UBB-IS-NOW.md` - the plain-English picture of the product as it stands.
3. `04-BILLING-READINESS-MATRIX.md` - what was verified, how, and where each proof lives.
4. `05-WHAT-ASH-INHERITS.md` - your register: what is done and not yours, and what is yours.

Then use as implementation/reference material:

- `02-TECHNICAL-SYSTEM-MAP.md` - the subsystem reference with `path :: Symbol (line)` citations at the proof anchor.
- `03-ASH-VALIDATION-AND-NEXT-STEPS.md` - the safe local recipe, the golden paths to re-run, the suites, and what
  cannot be demonstrated locally.

`R10-ASH-HANDOFF/` (2026-11-02) is the superseded historical handoff; do not work from it.

## B. Exact current identities

| Identity | Value |
|---|---|
| Current repository `main` | `90d008b709a86ff0d63588d8dd6b0a160978230b` |
| Behavioural proof anchor (Stage D) | `a6738e78e96ab10eabd45dc10fafdc842b7de519` |
| SDK release | `sdk-v5.0.0` (annotated tag) |
| SDK release commit | `b41b395f59d798cec83289d83d5ec71f83201c7f` |
| SDK wheel | `ubb_sdk-5.0.0-py3-none-any.whl` |
| SDK wheel SHA-256 | `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948` |
| W7 status | `PRE-LAUNCH — NOT FINAL` |

The three SHAs are distinct on purpose. The billing behaviour was proven on `a6738e78…`. The two commits after it
(#632, #633) are documentation and release-record changes only and changed no behaviour; `sdk-v5.0.0` is tagged on the
first of them and the current `main` is the second. The wheel lives in `R10-SDK-V5-RELEASE/` and is not on PyPI.

## C. What we proved

On the proof anchor, every billing golden path was re-run locally with a complete, union-proven test run and in a clean
environment (the F-16 lock pins): prepaid wallets under both the `off` and `enforcing` spend-control modes; postpaid
invoicing and payment recovery; plans and subscriptions (access and per-seat fees as Stripe Prices, seat reconciliation);
referrals with exact units; refunds and idempotency (a replay answers the same refund); the wallet perimeter, including
honest no-wallet semantics for tenants without one; both Stripe webhook receivers with receiver-scoped dedup and
reprocessing; manual holds and the audit actions behind them; postpaid and seat reconciliation; SDK 5.0.0 end to end,
including the generated core; the console and the Code Builder codegen. Every Stage B finding is repaired and re-proven
(`04`). Nothing in the Stripe path left the process: real Stripe objects were exercised under a local sentinel key with
transport blocked.

`BILLING BLOCKER: 0`

`PRE-ASH REQUIRED FIX: 0`

## D. What we did NOT prove

This package is NOT:

- production deployment evidence - nothing has ever been deployed;
- real payment-rail activation evidence - no `PaymentRailActivation` exists outside disposable test databases;
- production Stripe or Connect evidence - no real test or live Stripe credential was used, no Connect account onboarded;
- public HTTPS receiver evidence - no webhook receiver is reachable from Stripe;
- production SLO evidence - local figures are not measurements;
- real-client admission evidence - no tenant is live.

Those are your work, under W7.

## E. What you do next

Work from `R10-W7-DELIVERY-PROMPT.md`. Its starting baseline now reads `90d008b709a86ff0d63588d8dd6b0a160978230b`,
but its STATUS is still `PRE-LAUNCH — NOT FINAL`: it must not be executed until the seven named launch inputs
(hosting provider/service, region, account holder, acceptance signer, first real tenant identity, governance
decision-maker, alert destination) are real and the accountable decisions are made, and its STATUS line reads FINAL.

Your lane, from `05-WHAT-ASH-INHERITS.md`: hosting and deployment (one immutable image, three roles, managed
PostgreSQL and Redis, the environment); log drain and alert destination; Stripe test credentials and real Level-2
verification; Connect onboarding and account readiness; the public billing and subscription webhook receivers; the
production/test Stripe environment layout; the Clerk production environment; production-host SLO 1-3; the native
required-check ruleset when repository-admin access permits (the temporary R10 merge guard was a compensating control,
not branch protection); the W7 acceptance and admission process; the first real tenant in `external` mode; the
accountable human decisions and signatures; and payment-rail activation only if and when a money-mode tenant is later
admitted. If the first client integrates through the Python SDK, W7 hands it `sdk-v5.0.0`, using the verified wheel in
`R10-SDK-V5-RELEASE/` (FINAL owner/consultant ruling, 2026-11-09; W7 §0.5 step 13). There is no unresolved internal owner
decision in this handoff; the remaining decisions are the W7 launch inputs and operational decisions, by design.

Programme disposition, 2026-11-09:

`R10 BILLING READINESS: INTERNAL PROGRAMME COMPLETE — HANDED FORWARD TO ASH`

`FINAL OWNER POLICY CLOSURE: first-client Python SDK = sdk-v5.0.0.`

That means the internal billing repair, the verification and handoff, and the SDK v5 release are complete. It does not
mean production-ready, W7 passed, a first customer admitted, or a rail activated.
