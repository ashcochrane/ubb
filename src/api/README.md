# API client + generated types

This directory holds:

- `client.ts` — typed openapi-fetch clients, one per backend namespace, whose relative paths are derived from the canonical API's absolute paths.
- `schema.json` — local snapshot of the backend's canonical `/api/v1/openapi.json` document. **Tracked in git.** Its diff is the reviewable UI contract.
- `generated/` — TypeScript types derived from the snapshot. **Gitignored** (`src/api/generated/*.ts`); regenerated locally and in CI.
- `types.ts` — convenience re-exports of generated component schemas.

## Regenerating

With the Django dev server running on `http://localhost:8000`:

```bash
pnpm api:regen      # fetch snapshots + generate types
pnpm api:fetch      # snapshots only (needs server)
pnpm api:generate   # types only (offline)
pnpm api:check      # regen + fail if `src/api/schemas` differs from committed state
```

`api:check` only meaningfully diffs `src/api/schema.json` (the tracked snapshot). `src/api/generated` is gitignored, so changes there never trip the check — they're rebuilt from the snapshot.

Feature `types.ts` files should derive from `PlatformSchemas` / `MeteringSchemas` / `BillingSchemas` (see `src/api/types.ts`) rather than redeclare shapes. Anything we add on top (UI-only fields, computed flags) lives next to the derived type.
