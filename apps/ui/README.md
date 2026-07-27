# UBB Tenant Console

The tenant-facing web console for UBB — usage metering, real-time spend control, customer margin,
and billing in front of Stripe. React 19 + Vite + TanStack Router/Query, typed end-to-end against
the backend's OpenAPI contract.

## Quick start

```bash
pnpm install
pnpm dev                # mock mode by default — no backend, no auth needed
```

### Modes

| Env | Effect |
|-----|--------|
| `VITE_API_PROVIDER=mock` (default) | Every feature runs on realistic in-memory fixtures |
| `VITE_API_PROVIDER=api` | Real backend at `VITE_API_URL` (dev proxy targets `localhost:8000`) |
| `VITE_CLERK_PUBLISHABLE_KEY` unset + mock | No-auth dev mode (auto session) |

## API contract

`src/api/schema.json` is the committed snapshot of the backend's `/api/v1/openapi.json`
(monorepo source of truth: `../../openapi/v1.json`). TypeScript types are generated from it into
the gitignored `src/api/generated/`:

```bash
pnpm api:generate   # types from the committed snapshot (offline)
pnpm api:sync       # refresh snapshot from ../../openapi/v1.json + regenerate
pnpm api:check      # fail if the snapshot drifts from the canonical spec
```

## Verify

```bash
pnpm test           # vitest (feature tests + route-tree smoke suite)
npx tsc -b          # strict typecheck
pnpm lint
pnpm build          # production build
```

## Orientation

Read `CLAUDE.md` for architecture, the feature-module pattern, contract sharp edges (micros money,
cursor pagination, open enums, problem+json), and the navigation model.
