# UBB

Usage, spend-control, and margin infrastructure for AI applications — the layer
between an AI app and Stripe.

- **UBB owns:** usage metering, real-time spend control, provider-cost &
  billed-cost tracking, customer margin analytics, and (for billing tenants)
  prepaid credit drawdown / period-close Stripe line-item push.
- **Stripe owns:** invoicing, payment collection, tax, dunning, customer portal,
  refunds, disputes, and subscription/seat lifecycle.

See `docs/architecture/positioning.md` and `docs/plans/2026-06-05-ubb-repositioning-design.md`.
