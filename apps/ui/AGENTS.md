# AGENTS.md — UBB UI

Supplement to CLAUDE.md with agent-specific instructions.

## Before Writing Any Code

1. Read `PROGRESS.md` — know current implementation status
2. Read `docs/superpowers/specs/2026-04-09-full-rebuild-design.md` — the master design spec
3. Read `docs/design/ui-flow-design-rationale.md` — understand page purposes, flows, and why decisions were made
4. Read the HTML mockup(s) for the feature you're building in `docs/design/files/`
5. Read `CLAUDE.md` — follow all patterns, dependency rules, conventions
6. Read `docs/architecture.md` and companion docs as needed for the task

## After Writing Code

1. Run tests: `pnpm test`
2. Run lint: `pnpm lint`
3. Run build: `pnpm build`
4. Verify no cross-feature imports
5. Update `PROGRESS.md` (only if implementation progress changed)
6. **Do NOT commit.** The user handles all git operations. Suggest a commit message instead.

## Rules

### Architecture
- Follow feature co-location pattern: `features/{name}/components/` + `features/{name}/api/`
- Follow provider pattern: every feature has types.ts, mock.ts, api.ts, queries.ts, provider.ts
- Follow dependency rules — imports flow DOWN only
- Never deviate from patterns without explicit user approval

### Components
- Build to match HTML mockups in `docs/design/files/` — these are the source of truth
- Components import from their feature's `queries.ts` — never from `api/client.ts`
- Route files are thin (<50 lines) — delegate to feature components
- No cross-feature imports
- shadcn components restyled via Tailwind only — don't edit the component files
- Loading states use skeletons, not spinners

### Data
- No `useEffect` for data fetching — use TanStack Query
- No `any` types
- All monetary values formatted via `lib/format.ts` — never divide by 1M inline
- Mock data in feature's `api/mock-data.ts` with `delay()` — never imported directly by components
- All forms use React Hook Form + Zod

### Design Principles
Every page must be **Fast** (3 clicks max), **Easy** (no unexplained jargon), and **Risk-free** (confirmations for destructive actions). See `docs/design/ui-flow-design-rationale.md` for details.

## When Stuck

1. Re-read the design spec: `docs/superpowers/specs/2026-04-09-full-rebuild-design.md`
2. Re-read the design rationale: `docs/design/ui-flow-design-rationale.md`
3. Check the HTML mockup for the feature you're building
4. Check the architecture docs in `docs/`
5. Ask the user before making architectural decisions not covered in docs
