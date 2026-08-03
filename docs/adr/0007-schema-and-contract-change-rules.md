# ADR-0007: Schema and contract change — what may move, and what must carry its data

**Status:** accepted
**Date:** 2026-08-03
**Decision record:** `docs/plans/2026-08-03-migration-and-cutover-decision.md` (#155) — the frozen
evidence, the eight-slice plan, the per-slice contract and the cutover step
**Supersedes:** ADR-0005's Migration note, whose warning becomes §1's rule with a check behind it
**Amends:** ADR-0003 §5, by naming the act that ends the pre-live lane (§5)
**Companion:** ADR-0006 owns *what things are called*; this ADR owns *how they are allowed to change*

## Context

The pricing and metering re-model (map #137) rebuilds the domain across eight slices and a cutover.
Most of that work is one-time and belongs in the decision record. A handful of the rules it establishes
are not one-time: they describe how this codebase changes a schema or a published contract, and they
keep binding long after the cutover is history.

They exist because the repository had already demonstrated each failure:

- Two migrations under the same pre-launch licence chose **opposite** techniques — `usage/0028` used
  `AddField` + `RemoveField`, `tasks/0004_the_clean_cut_run_to_task` used `RenameModel` / `RenameField`
  — so the tree taught both, and ADR-0005 was reduced to warning readers not to copy one of them.
- `UsageEvent.save()` raised on update while `QuerySet.update()` sailed past it, with one production
  writer using the second door and a docstring asserting the first door made the row immutable.
- Three SDK methods called routes that existed in no spec and no router, green in CI for months,
  because nothing compared the hand-written client to the contract it claimed to implement.
- The `api-v1-launch` tag was cut, then treated as not-quite-binding, with the judgement call recorded
  in prose in three separate documents.

Map #137 constraint 1 — **no live integrators** — buys one clean break to fix all of it. That freedom
expires the moment someone integrates, which is why §5 makes the expiry an act rather than an
observation.

## Decision

**A schema change carries its data, a contract change is generated and reviewed, and a record's
mutability is declared per field and enforced by the database — never asserted in a docstring.**

---

### 1. A migration that renames or moves a column carries its data

From the cutover squash onward:

- Renaming a column or a model uses `RenameField` / `RenameModel`, never `AddField` + `RemoveField`.
- Moving data between columns, tables or representations carries an explicit `RunPython` with a
  reverse where one is possible.
- Dropping a column that may hold rows requires a **stated reason in the migration**, in the style
  already used by `tasks/0004`.
- A table rename preserves rows, primary keys, foreign keys, indexes, constraints and sequences. It is
  never a drop-and-recreate.

**Backed by a check**, not by a note. ADR-0005's Migration note existed precisely because a note is
what a future engineer reads after they have already copied the pattern.

**Before the squash this rule does not apply**, and the decision record says why: the operational rows
were destroyed by a merged decision (#153 §13) and nothing was deployed, so carrying them would have
served no one. That exemption is spent. It is not available again.

---

### 2. Mutability is declared per field, and the database enforces it

No record claims to be "immutable" as a whole. A record that holds economic facts is **economically
protected with controlled lifecycle mutations**, and every column is declared into exactly one class:

| Class | Permitted transition |
|---|---|
| **FROZEN** | none after insert |
| **RESOLVE_ONCE** | unresolved/`NULL` → one terminal value, exactly once; then frozen |
| **SET_ONCE** | `NULL` → value, once |
| **PRUNABLE** | populated → `NULL`/pruned marker, after the declared retention horizon only |

**RESOLVE_ONCE is the load-bearing one.** `NULL` and `0` stay distinguishable — `NULL` is *not
resolved*, `0` is *resolved as exactly zero*. A status and its amount transition **atomically**.
Application code resolves with a conditional update asserting exactly one affected row:

```sql
UPDATE ... SET amount_micros = %s, status = 'known'
 WHERE id = %s AND amount_micros IS NULL AND status = 'unresolved'
```

This is the schema expression of a distinction the domain already makes: **resolution completes
previously unknown information; correction changes a value that was already asserted.** Completing a
blank is permitted once. Replacing a known value is prohibited and must be a separate record beside the
original.

**SET_ONCE is not "append-only".** A column described as append-only invites an implementation that
rewrites a list on each write, under which two concurrent writers silently overwrite each other. If
several independent annotations must be preserved, they are **separate append-only child records**,
never a repeatedly rewritten array.

**PRUNABLE removes detail; it never rewrites history.** A pruned column is never repopulated with
different historical content, and pruning may never change a resolved amount, an economic status, the
currency, the canonical attribution, or the inputs a receipt needs to explain its own figure.

**Enforcement is two-layered, deliberately.** The service layer provides the commands, the validation,
the friendly errors and the atomic conditional update. **The database rejects forbidden `OLD → NEW`
transitions regardless of the path** — `save()`, `QuerySet.update()`, admin scripts, management
commands or background jobs. A model-level guard alone is not enforcement; the repository has already
shipped one that a production writer bypassed by design.

Tests attempt **every prohibited transition through both ORM update paths and through direct SQL.**

---

### 3. No provisional public vocabulary

Anything added to `openapi/v1.json` ships under its **final** name and final contract, even where the
implementation behind it is only partly built.

A change must not expose a temporary public shape merely because part of its internals has landed.
Doing so guarantees a second breaking change later whose only purpose is to repair the first one's
placeholder. Internal scaffolding is permitted; public scaffolding is not.

---

### 4. The contract and its clients are checked mechanically, in both directions

**Accepted contract breaks are generated, never hand-written.** Entries in the `oasdiff` suppression
files come from running `oasdiff`. A reviewed block may carry human metadata — date, PR, decision
reference, and the reason the break is accepted — but never a hand-typed finding. Hand-derivation has
already put WARN-level entries into the ERR-ignore file, where the flag silently did nothing for them,
while missing ERR findings entirely.

**Every hand-written SDK call targets a real operation.** The check validates the complete operation
identity — HTTP method plus normalised path, or preferably the OpenAPI `operationId`. A path match
alone is insufficient: `GET /x/{id}` is not `POST /x/{id}`.

**Every published operation carries an explicit SDK disposition** — `wrapped`, `generated_only` or
`not_yet_wrapped` — in a generated manifest that must stay mechanically accurate. The count of
unwrapped operations is not required to be zero; an *increase* must be an explicit reviewed change
rather than an accidental omission.

**Route literals live in one checked place.** A hand-written client method references a generated
operation or an operation registry rather than carrying its own `"/api/v1/..."` string, so a route
rename cannot leave a stale client string behind.

---

### 5. The pre-live lane ends by an act, not by a date

ADR-0003 §5 binds the v1 contract "at self-serve launch". `docs/api-compatibility.md` already states
the sharper version — *"The existence of the tag is not, by itself, the thing that binds; a consumer
depending on the contract is."* This ADR makes that operational:

- **Admitting the first integrator is a deliberate act**, gated on the end-to-end audit (#158) passing.
  The repository supports this today because no API route creates a tenant; admission is already
  manual and cannot happen by accident.
- **Until that act, the dated status note in `docs/api-compatibility.md` stays**, and breaking edges
  are coordinated by hand through the suppression files.
- **From that act, ADR-0003 §4 governs with no further judgement calls** — `deprecated: true`, a
  `Sunset` header, a dated changelog entry, an email, and 90 days' notice, on every breaking change.
- **The note's deletion is the record of the act**, not an afterthought to it.

The pre-live allowance is a licence with one use remaining. Spending it is what map #137 is doing; §1
through §4 exist so that nothing needs it again.

---

## Consequences

- **A future model rename carries a table-rename migration.** #154 §6.1 already accepted this as
  desirable: the database should not preserve obsolete terminology indefinitely.
- **Declaring a field's transition class is a design decision at model-definition time**, and adding a
  column now means answering "what is allowed to happen to this?" before it ships. That is the cost,
  and it is the point.
- **Database-enforced transitions have a per-insert and per-update cost on the hottest path in the
  system.** Which mechanism carries them — triggers, `CHECK` constraints, rules — is an implementation
  decision, and its cost should be measured rather than assumed.
- **The SDK's ergonomic hand-written layer survives.** §4 puts a mechanical invariant behind review
  rather than replacing the layer with generated code; the layer has product value and the Code Builder
  (#156/#157) targets it.
- **§3 makes partial delivery slower and second breaks impossible.** A change that cannot yet name a
  thing correctly does not publish it at all.
- **§5 gives the compatibility promise an owner.** The risk it names is not that a migration fails; it
  is that someone is admitted before the system was proven, which is now a decision with a name on it.
