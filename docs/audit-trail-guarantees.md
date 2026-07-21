# Audit-Trail Guarantees — who changed this, and when

> **Decided in [#68](https://github.com/ashcochrane/ubb/issues/68) →
> [ADR-004](adr/0004-tenant-audit-trail.md). Built in
> [#81](https://github.com/ashcochrane/ubb/issues/81) (the kernel ledger) +
> [#82](https://github.com/ashcochrane/ubb/issues/82) (the record() sweep, CI pin, and feed).**

UBB keeps a durable, tenant-scoped record of *who did what, when, to which resource* on your
account — separate from the wallet ledger (which proves money conservation) and from the webhook
outbox (a processing queue that ages out). This document is the published contract for that record:
what is captured, who can read it, and how long we keep it.

Every statement below is **Live**: on `main`, enforced by a database model, application code, or a
named test pin.

---

## 1. What is recorded

Every **principal-initiated mutation** of your account records one append-only entry, in the same
database transaction as the change — so a rolled-back change leaves no phantom entry, and a
committed change always leaves one. Coverage spans:

- **Governance / config** — tenant config (including `enforcement_mode`), rate cards, rates,
  markups, budgets, billing profiles, auto-top-up, postpaid config, margin thresholds, revenue
  profiles, webhook configs, plans, referral programs, Stripe Connect start, sandbox provisioning.
- **Membership & key lifecycle** — invitations created/revoked, member roles changed, members
  removed, API keys created/rotated/revoked.
- **Hand-moved money** — manual credits, debits, withdrawals, refunds, credit grants and voids, and
  customer top-ups (tenant- and widget-initiated).
- **Customers & subscriptions** — customers created, subscriptions created/canceled/paused/resumed,
  seat counts changed.

**Not recorded** (by decision, ADR-004 §3): **usage ingestion** — `POST /metering/usage[/batch]`,
`/metering/usage/ingest`, task close, and the spend pre-check. That is high-volume telemetry, not
governance; it would swamp the trail and is already visible on the usage ledger and via webhooks.
Reads are never recorded.

**The sweep is enforced, not trusted.** A CI pin (`api/v1/tests/test_audit_sweep.py`) walks every
mutating route on the API and fails unless the route records an audit action or is on a short,
reviewed exemption list. A new mutation added without an audit entry turns CI red — the ledger
structurally cannot fall behind the surface.

## 2. What each entry contains — and what it never contains

Each entry carries the **actor**, the **action name**, the **target resource** (type + id), the
**timestamp**, the request's **correlation id** (linking it to any webhooks the same request
emitted), and a small **hand-curated metadata** dict chosen per action (e.g. a budget change
carries the new cap).

There is **no automatic before/after snapshot**. Because nothing is captured indiscriminately,
secrets — webhook signing secrets, raw API keys or their hashes, OAuth nonces, referral link tokens
— **structurally cannot reach this permanent table**.

**Actor kinds** are an open enum (tolerate it growing): `member`, `api_key`, `operator` (all UBB
support actions render under one name, **"UBB operator"**), and `end_customer` (widget-initiated
top-ups). `system` is reserved for future system-initiated actions. Every entry stores the actor id
**plus a display snapshot taken at action time**, so a later rename or deletion never rewrites
history.

## 3. Who can read it

One cursor-paginated endpoint — `GET /api/v1/audit/records`, in the committed OpenAPI spec — with
the standard `{data, next_cursor, has_more}` envelope. Optional `action` and
`resource_type`+`resource_id` filters answer "who changed *this* rate card?".

**Any tenant principal, at any role, may read the feed** — a **Read** floor. Audit visibility is
transparency, not power; the dangerous verbs already require Admin. **End-customer widget tokens
are not tenant principals and cannot read it** (they authenticate only the `/me` surface).

## 4. Retention — the published floor

**We keep everything, and promise to retain audit entries for at least one year.**

This is a **floor: raisable, never lowerable** (ADR-003 §3's rule for published promises). There is
no pruning job today — audit volume is governance-scale, not telemetry-scale — and the one-year
floor leaves room to introduce pruning someday without breaking this commitment. Log-style
90/180-day retention was rejected on purpose: "who changed this rate card?" gets asked at renewal
and dispute time, a year later.

## 5. Sandbox

Sandbox actions are audited exactly like live ones (scoped to the sandbox tenant you authenticate
against with a `ubb_test_` key). A **sandbox reset clears the sandbox's own audit entries** — as it
clears all sandbox data — and **is itself recorded** as the first entry of the fresh history,
attributed to the principal that triggered it. Your live account's trail is never touched by a
sandbox reset.
