# ADR-004 — The tenant audit trail: a kernel ledger of named actions

**Date:** 2026-07-20 · **Status:** accepted · **Decided in:**
[#68](https://github.com/ashcochrane/ubb/issues/68) (grilling session)

## Context

Nothing today answers "who did that, and when" for a tenant's account. Actor attribution exists in
exactly two ad-hoc places — `Refund.refunded_by_api_key` (a real FK) and
`WalletTransaction.actor` (a caller-supplied free-text string on the manual debit/credit escape
hatch, unexposed by any API). Rate cards version temporally (`valid_from`/`valid_to` — *when* and
*what* are reconstructable) but record no *who*, anywhere.

The obvious raw material fails on inspection. The outbox is an **ephemeral processing queue, not a
record**: processed rows are hard-deleted after 30 days (skipped after 90), a sandbox reset
deletes a tenant's rows outright, and — decisively — its coverage is wrong for auditing. Events
fire for money/usage flow and API-key lifecycle, but essentially **all config governance mutates
silently**: rate cards, markup, budgets, billing profile, auto-top-up, credit grants, webhook
configs, tenant config including `enforcement_mode`, customers/plans/seats. Exposing the outbox as
the feed would miss exactly the who-changed-what-when material an audit trail is for.

Meanwhile [#62](https://github.com/ashcochrane/ubb/issues/62) means real principals exist from
launch day — members and API keys with Admin/Write/Read roles — so "who" has meaning, and the
plumbing for capturing it exists: one auth choke point (`core/auth.py`) and a proven
request-scoped-contextvar pattern (`correlation_id`, captured once, read centrally by
`write_event` with zero call-site changes).

## Decision

### 1. The full feature ships in the v1 launch surface

Both halves — durable recording *and* the tenant-facing activity feed — are in the launch surface.
(The fallback posture, record-now-expose-later, was considered and rejected by the driver: the
feed ships.)

### 2. Mechanism: named audit actions into a durable kernel ledger, gated by a CI pin

A new append-only ledger records explicit, **named audit actions** (`rate_card.published`,
`budget.updated`, `webhook_config.deleted`, …) written at each mutation site — the `write_event`
calling pattern. The actor is captured **once**, at the auth seam, into a request-scoped
contextvar and read at record time; mutation sites never pass "who" by hand.

The action names form a **registry that is part of the public contract**: additive-only, a rename
is a breaking change — the same compatibility algebra as the
[#63](https://github.com/ashcochrane/ubb/issues/63) error-code registry, under ADR-003's rules. Names are domain vocabulary, deliberately decoupled from routes: the pending
single-API restructure (ADR-002) renames routes; it must never rewrite history's vocabulary.

The known failure mode of explicit instrumentation — a new endpoint that forgets to record — is
closed structurally, the house way: a **CI pin walks every mutating route and fails unless the
route records an audit action or is explicitly exempted** (the ADR-001 boundary-walker /
catalog==schemas move: discipline becomes a gate).

Rejected alternatives: **auto-logging every write request** at middleware (complete by
construction but mechanical — entries keyed to routes a restructure will rename, and a readable
feed needs a route→description mapping maintained forever, i.e. the registry built reactively and
worse); **riding the outbox** (welds the audit trail to the contractual webhook catalog — every
audit-worthy action would grow the public event surface or need an internal-only event tier that
doesn't exist — and queue semantics keep leaking into ledger semantics). The outbox remains what
its glossary entry says it is: a cross-product integration channel. **Queue and ledger stay
separate concepts.**

### 3. Scope: every principal-initiated mutation; telemetry and system actions out

In scope: all settings/governance changes (pricing, markup, budgets, billing profile,
auto-top-up, webhook configs, tenant config, customers/plans/seats), membership and key lifecycle,
and **hand-moved money** (manual credits/debits, refunds, grants) — the audit row records *who*,
coexisting with the wallet ledger, which proves conservation. This supersedes the free-text
`WalletTransaction.actor` stub as the attribution record.

Out of scope: **usage ingestion** (high-volume telemetry, not governance — it would swamp the
ledger) and, for v1, **system-initiated actions** (auto-top-up firing, suspensions, patrol
repairs) — already tenant-visible via webhooks, addable later additively as an `actor_kind` the
open enum reserves (§4). Reads are never audited.

### 4. Entries: basics plus a curated summary — never automatic snapshots

Every entry: actor, action name, target resource (type + id), timestamp, and the request's
**correlation id** (linking the entry to any outbox events the same request emitted). On top, each
mutation site attaches a small **hand-chosen metadata dict** (e.g. `budget.updated` carries the
new limit). There is **no automatic before/after capture** — secrets (webhook signing secrets, key
material) structurally cannot reach a permanent table because nothing is captured
indiscriminately. Per-action diffs can be added later, additively.

**Actor kinds — four from day one**, in an open enum with `system` reserved: `member`, `api_key`,
`operator` (rendered "UBB operator" in the feed — support actions on an account are exactly what
an audit trail is for), and `end_customer` (widget top-ups, completing the money story). Every row
stores the actor id **plus a display snapshot taken at action time**, so later renames or
deletions never corrupt history.

Entries are written **in the same database transaction as the change** — a rolled-back mutation
leaves no phantom row.

### 5. Retention: keep everything; promise at least one year

No pruning job in v1 — volume is governance-scale, not telemetry-scale. The published contract
promises retention of **at least 1 year**: a floor, raisable never lowerable (ADR-003 §3's rule),
leaving room to introduce pruning someday without breaking a commitment. Log-style 90/180-day
retention was rejected — "who changed this rate card" gets asked at renewal and dispute time, a
year later.

Sandbox: sandbox actions are audited like live ones; a **sandbox reset clears sandbox-scoped
entries** (as it does all sandbox data) and **is itself recorded** as an entry that survives.

### 6. Placement: platform kernel — `apps/platform/audit`

A new kernel module, **sibling to `apps/platform/events`**, exposing one `record()` surface that
any product or composition-layer endpoint calls directly — the `write_event` pattern, and the
[#62](https://github.com/ashcochrane/ubb/issues/62) precedent (Member rows in the kernel:
infrastructure every product needs isn't a fifth product). Not inside `events/` — co-housing would re-blur the queue-vs-ledger line §2 draws. Not a
fifth product — ADR-001 channels would force every product to reach it through the mechanism §2
rejects. ADR-001 is respected, not amended.

### 7. The feed: one cursor-paginated endpoint, readable by every tenant principal

The feed API follows the contract decisions wholesale: cursor pagination with the
`{data, next_cursor, has_more}` envelope ([#63](https://github.com/ashcochrane/ubb/issues/63)),
action names as an **open enum** clients must tolerate growing (ADR-003 §2), the endpoint in the
committed spec under the ADR-002 ratchet, SDK support via the generated core
([#65](https://github.com/ashcochrane/ubb/issues/65)) — no bespoke client.

**Access: any tenant principal — any role — can read the feed.**
[#62](https://github.com/ashcochrane/ubb/issues/62)'s one-line rule ("Read sees
all, incl. money") survives with zero exceptions, against the GitHub/Stripe admin-only posture:
audit visibility is transparency, not power — the dangerous verbs already require Admin.
End-customer widget tokens are not tenant principals and cannot read it.

## Consequences

- The action-name registry joins the compatibility contract: additive-only, renames are breaking,
  enforced by the ADR-002 gates once the feed is in the spec.
- The 1-year retention promise joins the published floors (with ADR-003's 90-day deprecation
  notice): raisable, never lowerable.
- Execution items for the program: the `AuditRecord` model + registry in `apps/platform/audit`,
  the auth-seam principal contextvar, per-site `record()` calls across the mutating surface, the
  mutating-route CI pin, the feed endpoint + spec + SDK pickup, sandbox-reset integration, ops
  attribution for operator actions, and the retention promise in the public compatibility docs.
- The ops surface gains a duty: operator mutations on a tenant's account must record like any
  other principal's.
- `WalletTransaction.actor` (free-text) stops being the attribution story; whether it is retired
  or left as a legacy column is an execution-time call.
- With #68 resolved, map [#60](https://github.com/ashcochrane/ubb/issues/60)'s decision phase is
  complete; what remains is the execution handoff.
