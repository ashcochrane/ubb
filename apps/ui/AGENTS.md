# AGENTS.md — UBB Tenant Console

Supplement to `CLAUDE.md` (which is current truth — read it first).

## Before writing any code

1. Read `CLAUDE.md` — architecture, feature-module pattern, contract sharp edges, navigation model.
2. Read the relevant slice of `src/api/schema.json` — the committed backend contract is the source
   of truth for every field, param, and status the UI touches.
3. Skim the feature's existing `api/` sextet and page components before adding to them.

## After writing code

1. `pnpm test` · `npx tsc -b` · `pnpm lint` · `pnpm build` — all four green.
2. Verify no cross-feature imports and no raw client calls from components.
3. Mock (`api/mock.ts`) stays signature-identical with `api/api.ts` and contract-typed.
4. Update `PROGRESS.md` only for genuine milestone changes.

## Git

Standard monorepo flow: feature branch → draft PR. (The standalone-era "never commit" rule is
retired; see the monorepo root `CLAUDE.md` for repo-wide conventions.)
