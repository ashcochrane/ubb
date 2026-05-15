# API client + generated types

This directory holds:

- `client.ts` — typed openapi-fetch clients, one per backend namespace.
- `schemas/` — local snapshots of each namespace's `openapi.json` (path prefixes stripped to match `client.ts` `baseUrl`). **Tracked in git.** Snapshots are the reviewable contract — diffs here are how backend changes surface in UI PRs.
- `generated/` — TypeScript types derived from the snapshots. **Gitignored** (`src/api/generated/*.ts`); regenerated locally and in CI.
- `types.ts` — convenience re-exports of generated component schemas.

## Regenerating

With the Django dev server running on `http://localhost:8000`:

```bash
pnpm api:regen      # fetch snapshots + generate types
pnpm api:fetch      # snapshots only (needs server)
pnpm api:generate   # types only (offline)
pnpm api:check      # regen + fail if `src/api/schemas` differs from committed state
```

`api:check` only meaningfully diffs `src/api/schemas` (the tracked snapshots). `src/api/generated` is gitignored, so changes there never trip the check — they're rebuilt from the snapshots.

Feature `types.ts` files should derive from `PlatformSchemas` / `MeteringSchemas` / `BillingSchemas` (see `src/api/types.ts`) rather than redeclare shapes. Anything we add on top (UI-only fields, computed flags) lives next to the derived type.
