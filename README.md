# UBB

Usage, spend-control, and margin infrastructure for AI applications — the layer
between an AI app and Stripe.

- **UBB owns:** usage metering, real-time spend control, provider-cost &
  billed-cost tracking, customer margin analytics, and (for billing tenants)
  prepaid credit drawdown / period-close Stripe line-item push.
- **Stripe owns:** invoicing, payment collection, tax, dunning, customer portal,
  refunds, disputes, and subscription/seat lifecycle.

See `docs/architecture/positioning.md` and `docs/plans/2026-06-05-ubb-repositioning-design.md`.

## Repository layout

- `ubb-platform/` — Django API and domain applications
- `ubb-sdk/` — Python SDK
- `apps/ui/` — React admin UI
- `openapi/v1.json` — the committed API contract shared by the platform, SDK,
  and UI

## Local development

Start PostgreSQL and Redis with `docker compose up -d`. The project maps them
to host ports 5433 and 6380 to avoid colliding with existing local services.

Run the API from `ubb-platform/` with `./.venv/bin/python manage.py runserver`.
The UI commands are available at the repository root:

```bash
pnpm ui:dev
pnpm ui:api:sync
```

`ui:api:sync` regenerates the UI's one tracked OpenAPI snapshot from the
committed `openapi/v1.json`; it does not require the API server to be running.
