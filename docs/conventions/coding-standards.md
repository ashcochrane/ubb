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
  Task → Wallet → Customer → TopUpAttempt → Invoice → Posting (`core/locking.py`). Violating it
  risks deadlock. Wallet mutations go through `lock_for_billing`.
- **`queries.py` returns plain data.** Cross-product read contracts return dicts/ints/lists, never
  ORM instances or querysets — so a product could later become a network hop.

## Vocabulary

**`domain-vocabulary/` is the oracle, and it is complete** (#202): every UBB-owned concept's exact
token and value set is declared there, CI enforces it (ADR-0008 §2), and the names are the ones
ADR-0006 fixed rather than the ones the tree carries today. Check an edit with
`python -m tools.vocabulary`. Read the registry BEFORE inventing a name — several words the older
prose in this repository still uses are retired there, and `retired_aliases` says what replaced each
one.

Every concept declares one of four kinds — `closed`, `open`, `tenant_defined`, `free_text` — and
`tenant_defined`/`free_text` carry no values by construction, because UBB never ships a catalogue of
the tenant's models, providers or grouping values.

For a concept's **meaning and relationships**, the per-product `CONTEXT.md` glossary is still the
place (via the root `CONTEXT-MAP.md`) — `drawdown` not "charge", `referred customer` not "referee".
If a concept is in neither, that's a signal — see `docs/agents/domain.md`.

Code **imports** a registry value; it never restates the literal. Each of the three consumers has its
own **generated** artifact — the banner says so on each, and a hand edit turns CI red:

| Consumer | Import from | Landed |
|---|---|---|
| Django platform | `core.vocabulary` | #200 |
| React console | `@/lib/vocabulary` | #207 |
| Python SDK | `ubb.vocabulary` | #207 |

Agreement is therefore structural rather than textual, which is why nothing scans source for matching
strings. Two names per set, and the difference binds: `<CONCEPT>_VALUES` is a `closed` concept and is
exhaustive; `<CONCEPT>_KNOWN_VALUES` is an `open` one, so a value missing from it is still legal and
that set must never decide a rejection (ADR-0003).

The console's artifact adds the stable label **keys** and, for an `open` concept, a type that admits
any string — so don't write an exhaustive `switch` over one. It never carries the English: that is
the console's own catalogue (ADR-0008 §4).

Editing the registry is therefore never enough on its own — regenerate in the same commit:

```
python -m tools.vocabulary --write
```

Where a value's canonical name is not yet the string in flight, **leave the literal alone**: renaming
a value a tenant can see belongs to the slice that owns it, with a migration-ledger entry (#201), not
to whoever happens to be editing the file.

### Writing a new module while a word is being retired

A migration-ledger entry records how many files still carry a retired word (`found: N files`). **That
number is a ceiling on SPREAD, not just a measure of what is left to fix** — a new module that names
the word puts the count over its entry and the forbidden-term sweep fails. Combined with the rule
that allowlists only ever shrink, this bites hardest on exactly the slice retiring the word, because
that slice is writing most of the new tests about it.

Three techniques, with precedent on `main`, **in order of preference**:

1. **Derive the retired name from the operation that retired it.** A `RenameField` carries
   `old_name` and `new_name`; a `RemoveField` carries the `name` it deletes. Read the name off the
   migration instead of typing it. Costs one import, takes no seeding authorisation, and has the
   second benefit of going red rather than stale if the operation ever changes.
   *Worked example:* `apps/metering/pricing/tests/test_the_rates_quantity_name_takes_the_canonical_name.py`,
   which unpacks its rename from a one-element tuple so that a migration growing a second
   `RenameField` fails loudly rather than silently picking one.
2. **Put the word once in a helper the sweep already counts, and have callers say what they mean.**
   A fixture helper that takes `measurement_key=` and resolves the plumbing behind it leaves every
   caller naming the domain rather than transcribing a column.
   *Worked example:* `apps/metering/pricing/tests/_helpers.py`, whose two doors pick a book so no
   caller anywhere names the kind word.
3. **Admit the file** to the sweep's `checks-whose-subject-is-a-retired-word` rule in
   `gates/forbidden-term-sweep.yaml`. The admission test is strict, and it is not about convenience:
   *not "this file is inconvenient" but "no slice will ever remove this word from this file, because
   naming it is what the file is for."* It costs a declared path and a count a reviewer sees in the
   diff.

**⚠ Explicitly rejected, so do not propose it:** moving a word into the registry's `retired_senses`
to escape the sweep. That disarms the gate across **every** surface at once, on the very slice
retiring the word.

**⚠ And the sweep is blind to three shapes, so grep them by hand on any commit that rewrites a
surface's vocabulary.** The matcher requires a non-identifier character on each side of the token as
the registry spells it, so it cannot see:

- **the spaced or hyphenated English form** — "rate card", "cost-card". This has now been paid for
  four times: in a console screen, in the SDK README, in a per-product glossary and in a published
  guarantees document, each time under a quickstart or a definition that had already been rewritten
  around it;
- **a Pascal-cased spelling**, because the match is case-sensitive;
- **a retired *sense*** — a word still live in another meaning, which is deliberately not input to
  the sweep at all. A ticket that greps for a token will not find one.
