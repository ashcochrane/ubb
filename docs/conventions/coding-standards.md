# Coding standards

Conventions this codebase already follows. There is **no automated formatter or linter** configured
(no ruff/black/flake8/pre-commit) — so the rule is: **match the surrounding style** (PEP 8-ish,
4-space indent, `snake_case` functions, `PascalCase` models, `UPPER_SNAKE` module constants and
`*_CHOICES` enums). The items below are the load-bearing ones that are not merely cosmetic.

## Import discipline (the one that's machine-enforced)

Products (`apps/{metering,billing,subscriptions,referrals}`) may talk to each other **only** through
the four sanctioned channels — outbox events, `queries.py`, `ports.py`, platform hooks. See
`../architecture/2026-06-12-adr-001-product-boundaries.md` and the `## Agent skills` block in the
repo-root `CLAUDE.md`.

- A stray cross-product import fails `apps/platform/tests/test_product_boundaries.py` in CI —
  including **lazy, function-body imports** (the AST walker catches those too). Don't reach for a
  function-scope import to dodge a circular dependency; that's the exact erosion the ADR documents.
- `apps/platform/**` and `core/**` never import a product. The composition layer (`api/v1`,
  `apps/*/api`) may import any product; products never import `api.*`.

## Money is integer micros

All money is `int` **micros** (one-millionth of a currency unit), stored and computed as micros with
half-up rounding.

- Never use `float`/`Decimal` for money in models or arithmetic. A Stripe cent is `10_000` micros.
- Money fields carry the `_micros` suffix (`balance_micros`, `provider_cost_micros`,
  `billed_cost_micros`). Keep the suffix — it's how a reader knows the unit.

## Errors: raise domain exceptions

Raise from the `UBBError` taxonomy (`core/exceptions.py`), never bare `Exception` for domain
conditions: `InsufficientBalanceError`, `CustomerSuspendedError`, `IdempotencyError`,
`RateLimitError`, and the Stripe split — `StripeTransientError` (retried), `StripePaymentError`
(card declined, non-retryable), `StripeFatalError` (auth/config/idempotency mismatch — parks work
as `failed_permanent`). The retryable-vs-fatal distinction drives real control flow, so map to the
right one.

## Exactly-once by idempotency key

Any operation that can be redelivered (event handlers, top-up charges, ledger writes) is made
idempotent with a deterministic key, e.g. `usage_deduction:{event_id}`, `auto_topup:{pi_id}`,
`expiry:{grant_id}`. A replay must be a no-op, not a double effect. Balance movements are always an
append-only **ledger entry** keyed this way — never a bare `balance += x`.

## Data-plane rules

- **Soft delete only.** Rows use `deleted_at` (`core/soft_delete.py`); hard delete through the ORM
  is unsupported. Default querysets hide deleted rows; use `all_objects` to see them.
- **Lock ordering is canonical.** When taking more than one row lock, acquire in the global order
  Task → Wallet → Customer → TopUpAttempt → Invoice → UsageEvent (`core/locking.py`). Violating it
  risks deadlock. Wallet mutations go through `lock_for_billing`.
- **`queries.py` returns plain data.** Cross-product read contracts return dicts/ints/lists, never
  ORM instances or querysets — so a product could later become a network hop.

## Vocabulary

Name things using the relevant `CONTEXT.md` glossary (per-product, via the root `CONTEXT-MAP.md`).
Use `drawdown` not "charge", `margin` not "markup", `Rate` vs `RateCard`, `referred customer` not
"referee". If a concept isn't in the glossary, that's a signal — see `docs/agents/domain.md`.
