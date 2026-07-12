# UBB Positioning & Tenant Modes

UBB is the usage, spend-control, and margin layer in front of Stripe. It never
moves money out and never holds cash; it maintains a credit ledger that mirrors
money Stripe has already collected.

## Tenant modes (`Tenant.billing_mode`)
- **meter_only** — track usage + provider/billed cost + dimensional tags + margin. No money, no gate.
- **prepaid** — meter + prepaid credit ledger + real-time spend gate + auto-top-up. Requires the `billing` product.
- **postpaid** — meter + period-close Stripe invoice line-item push. Requires the `billing` product.

## Boundary
UBB owns everything up to invoice line items / credit drawdown. Stripe owns
invoicing, payments, tax, dunning, portal, refunds, disputes, and subscription/
seat lifecycle. Full detail: docs/plans/2026-06-05-ubb-repositioning-design.md.
