# UBB Positioning & Tenant Modes

UBB is the usage, spend-control, and margin layer in front of Stripe. It never
moves money out and never holds cash; it maintains a credit ledger that mirrors
money Stripe has already collected.

## Tenant modes (`Tenant.billing_mode`)
- **meter_only** — track usage + provider/billed cost + declared grouping fields + margin. No money, no gate.
- **prepaid** — meter + prepaid credit ledger + real-time spend gate + auto-top-up. Requires the `billing` product.
- **postpaid** — meter + period-close Stripe invoice line-item push. Requires the `billing` product.

## Boundary

UBB is a **control plane** over Stripe Billing, not a reimplementation of it and not a passive
mirror. Every piece of Stripe-owned state UBB stores is a cache: it has a refresh path, a staleness
bound, and it never decides money on its own.

| Concern | Owner | Rationale |
|---|---|---|
| Proration, invoicing, dunning, tax, retries | **Stripe** | Solved; never rebuild |
| Subscription status, amounts, periods | **Stripe** | One authority. UBB caches it, refreshed by webhooks + a scheduled reconciler |
| Seat *identity*, usage, provider cost, markup, margin | **UBB** | Stripe structurally cannot know these |
| Plan definition + assignment | **UBB kernel** | The only object spanning both engines |

UBB drives the subscription lifecycle (subscribe, seats, cancel, pause, resume, plan provisioning,
price versioning) as calls into Stripe; it never reimplements the billing engine itself. Full
detail: `docs/plans/2026-07-27-plan-as-kernel-design.md` §4. (The 2026-06-05 repositioning decision
that assigned the lifecycle to Stripe alone was reversed four days later by the J2 program's
`SubscriptionOrchestrator` — see `docs/plans/2026-06-10-program-current-state.md`.)
