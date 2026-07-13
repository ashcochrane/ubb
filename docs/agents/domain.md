# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase. **This repo is multi-context** — see `CONTEXT-MAP.md` at the root.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — it lists the product contexts and where each one's
  `CONTEXT.md` lives (`ubb-platform/apps/<product>/CONTEXT.md`). Read each `CONTEXT.md` relevant
  to the topic.
- **ADRs** — read decisions that touch the area you're about to work in. In this repo they live
  in **two** places:
  - `docs/adr/` — new, sequential ADRs (`0001-slug.md`).
  - `docs/architecture/` — the existing, richer architecture decisions, notably
    `2026-06-12-adr-001-product-boundaries.md` (the product-boundary matrix) and
    `two-product-separation.md`.

If any of these files don't exist yet, **proceed silently**. Don't flag their absence; don't
suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and
`/improve-codebase-architecture`) creates them lazily when terms or decisions actually resolve.

## File structure (multi-context)

```
ubb/                                   ← repo root
├── CONTEXT-MAP.md
├── docs/
│   ├── adr/                           ← new system-wide decisions
│   └── architecture/                  ← existing architecture decisions (incl. ADR-001)
└── ubb-platform/apps/
    ├── platform/CONTEXT.md
    ├── metering/CONTEXT.md
    ├── billing/CONTEXT.md
    ├── subscriptions/CONTEXT.md
    └── referrals/CONTEXT.md
```

## Use the glossary's vocabulary

When your output names a domain concept (an issue title, a refactor proposal, a hypothesis, a test
name), use the term as defined in the relevant `CONTEXT.md`. Don't drift to synonyms the glossary
explicitly avoids. If the concept you need isn't in the glossary yet, that's a signal — either
you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for
`/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-001 (product boundaries) — but worth reopening because…_

The product-boundary ADR is **machine-enforced**: a contradicting import fails
`apps/platform/tests/test_product_boundaries.py` in CI, not just disagrees with prose. Treat it as
a hard constraint, not advice.
