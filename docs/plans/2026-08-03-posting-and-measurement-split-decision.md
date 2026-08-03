# The posting and the measurement — one durable economic record, one prunable detail record

**Resolves:** [#165](https://github.com/ashcochrane/ubb/issues/165) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-03
**Decided against:** `main` @ `0cf00b5`
**Builds on:**
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the `Charge` is canonical and
projects 1:1 onto one marked posting, *because every correction path is keyed on a usage-event id*;
that reason is re-examined here and survives.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — unknown revenue ≠ zero revenue;
§1.2 handed the non-nullable `billed_cost_micros` defect to #147 and flagged the two-jobs shape.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — only declared measurements may
move money; §7.2 every row *owning* an amount stores its currency; **§14 raised this ticket.**
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — preserve, flag, remediate;
`provider_cost_micros` becomes nullable; *"the nullable column is what buys in-place resolution"*.
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — revenue has three states;
`billed_cost_micros` becomes nullable with a `pricing_status` beside it. **This ticket's blocker.**
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the receipt is authoritative and carries
values not pointers; six-year retention; §16 called this ticket's split *"the strongest argument yet"*.
`docs/plans/2026-08-02-charging-modes-decision.md` (#151) — §11 one money path: *a Charge explains
money; only its projected posting moves it*; §8 `not_applicable_reason`.
`docs/plans/2026-08-03-analytics-realignment-decision.md` (#153) — margin is a bucket-level
subtraction; **§2.3 analytics reads revenue off the posting, never off the `Charge`**; §12.4 two
retention clocks.
`docs/plans/2026-08-03-vocabulary-lock-decision.md` (#154) + `docs/adr/0006-domain-vocabulary-and-contract-naming.md`
— `kind ∈ {metered_usage, task_charge}`; `usage_metrics → measurements`; `pricing_provenance →
pricing_receipt`. **ADR-0006 is the living authority every name below is assessed against.**
`docs/plans/2026-08-03-migration-and-cutover-decision.md` (#155) + `docs/adr/0007-schema-and-contract-change-rules.md`
— §6 "immutable" leaves the posting; four transition classes enforced at the database. **This document
amends §6.3.**

**Status:** decided. Planning only; implementation is out of scope for map #137.

**No new ADR.** ADR-0006 and ADR-0007 already exist and are the living authorities. This document
proposes two names and one model rename, each assessed against ADR-0006's seven rules in §11, and
amends ADR-0007's transition-class table in §4. Both amendments are recorded there rather than in a
third ADR.

---

## The decision in one paragraph

**The row splits — but not in the direction the ticket assumed, and for only one of the three reasons
it offered.** The ticket costed the split by counting readers of `billed_cost_micros`: 30 non-test
files across all five products, four correction paths keyed on a usage-event *identity*, and a public
path parameter. That is the cost of moving the **economic** half. The measurement half — the thing
that actually wants to leave — is read by **7 files, every one of them inside metering or the API
layer**, keys no identity anywhere, and is written at a **single** insert site. So the identity stays
exactly where it is: the durable economic **Posting** keeps the id that refunds, wallet drawdown,
`WalletTransaction`, the cost lookup and `GET /metering/usage/{event_id}` already point at, and the
bulky measurement payload moves to an optional child record with its own, shorter clock. **The
load-bearing reason is retention and only retention** — two published clocks (#148's six-year receipt
floor, #153 §12.4's measurement horizon) cannot honestly share one row, and expressing them as a
column null-out forces the durable economic record to be *mutated* by a housekeeping job, which is
precisely what #155 §6 spent a section making impossible. As two records, pruning is a child-row
`DELETE` that never touches the posting, and **`PRUNABLE` leaves the posting's transition classes
entirely**. The child is **absent by construction** for a `task_charge` posting, which has no
measurements and no supplier cost at all (#154 §3.8) — so the split also stops manufacturing an empty
record merely so a fixed-price charge can possess an id. Absence therefore acquires two causes and
must say which, so the API carries **`measurements_status ∈ available | pruned | not_applicable`** —
the fourth time this map has refused to let one blank stand for two facts. #139's `Charge` does **not**
collapse into the posting: the Charge explains the liability, the posting moves it, and #153 §2.3
already forbids a second aggregation path over `Charge` rows.

---

## 1. The ticket's cost framing measured one direction only

### 1.1 The two halves are not remotely the same size

The ticket's "what makes this expensive" is exact and verified — and it measures the wrong half.

| | Economic half | Measurement half |
|---|---|---|
| Representative column | `billed_cost_micros` | `usage_metrics` |
| Non-test files reading it | **30** (34 incl. migrations) | **7** (incl. the model and the dev seeder) |
| Products it reaches | metering, billing, subscriptions, referrals, platform | **metering only** |
| Identity-keyed paths | **4** | **0** |
| Public path parameter | `GET /metering/usage/{event_id}` | none |
| Aggregated in analytics | continuously | **never** |

The seven files, and what each actually does:

```
api/v1/metering_endpoints.py:258       one serialisation line
api/v1/schemas.py:71,74,176,250        field declarations + a non-negative validator
apps/metering/pricing/.../pricing_service.py   reads it at rating time, in-process
apps/metering/usage/services/usage_service.py  writes it at record time
apps/metering/usage/services/ingest_accept.py  writes it — DELETED ENTIRELY by #149
apps/metering/usage/models.py          the column
.../commands/seed_dev_data.py          dev fixture
```

`ingest_accept.py` is removed in full by #149 §6, so the live count after slice 1 is **six**, of which
two are the model and the seeder.

### 1.2 The four correction paths do not move — they already point at the economic half

The ticket says *"each of these must decide which half it points at — and for all four the answer is
almost certainly the posting, not the measurement."* That is right, and it is the whole argument. If
the posting keeps the id, **none of them decides anything, because nothing changes**:

| Path | Site | Under this decision |
|---|---|---|
| `Refund.usage_event` `OneToOneField` | `usage/models.py:148-150` | unchanged — points at the posting |
| `usage_deduction:{usage_event_id}` exactly-once key | `wallets/operations.py:478` | unchanged — the id is the posting's |
| `WalletTransaction.usage_event_id` pinned column | `wallets/models.py:80` | unchanged |
| `get_usage_event_cost(usage_event_id)` | `metering/queries.py:75` | unchanged — cost lives on the posting |

The `usage_deduction:{id}` key deserves the explicit statement, because it is the one place where
getting this wrong is unrecoverable: **the exactly-once drawdown key keeps meaning exactly what it
means today.** A split that re-pointed it would silently re-key every historical wallet deduction, and
the failure mode is a double drawdown against real customer money.

### 1.3 What this does to the decision

The ticket presents "does the row split at all?" as a cost/benefit judgement in which the deliberate
"no" is the cheap option. Once the two halves are measured separately, the cheap option and the split
option are **nearly the same price**, and they are both far cheaper than the direction the ticket
assumed. The question stops being *can we afford it* and becomes *what does it buy* — which is §3.

---

## 2. The split, and where the identity stays

### 2.1 The ruling

**One durable economic Posting, keeping the existing identity, with an optional one-to-one
short-retention measurement record.**

```
Posting — durable, six-year economic record
  id                          <- THE identity. Unchanged.
  tenant, customer, task
  event_type, provider, kind: metered_usage | task_charge
  effective_at, created_at
  currency
  provider_cost_micros, costing_status
  billed_cost_micros,  pricing_status, not_applicable_reason
  pricing_receipt
  attribution / grouping fields
  stop_context
  charge_id                   <- unique; non-null for kind = task_charge (§7)

PostingMeasurement — shorter analytical retention, 0..1 per posting
  posting_id  UNIQUE
  measurements
  units                       <- see §9
  recorded_at
  prunable_at
```

Everything that identifies, explains, moves or counts money stays on the parent. The child holds only
detail that may legitimately expire: raw measurement quantities, measurement-level drill-down,
Measurement Concept analytics.

```
An ordinary metered call            A delivered fixed-price Task
  Posting                             Posting
    kind: metered_usage                 kind: task_charge
    supplier COGS                       billed revenue
    pricing result                      pricing receipt
    durable economic identity           durable economic identity
  PostingMeasurement                  PostingMeasurement
    input_tokens: 1200                  ABSENT BY CONSTRUCTION
    output_tokens: 340
    searches: 2
```

### 2.2 The child is absent by construction, never empty

A `task_charge` posting has no measurements and no supplier operation behind it. #154 §3.8 states this
as a reporting contract, not a convention:

| | `metered_usage` | `task_charge` |
|---|---|---|
| Represents a provider operation | yes | **no** |
| May carry measurements and supplier COGS | yes | **no** |
| Appears in measurement analytics | yes | **excluded** |

Today that row still stores `usage_metrics = {}`, `units = NULL`, `provider = ""` and
`provider_cost_micros = 0` — four columns that can never apply to it, one of which (`provider_cost_micros
= 0`) states a supplier cost of zero for something that never had a supplier. Under the split the
child record **simply does not exist**, which is a stronger statement than an empty one and needs no
convention to interpret.

The owner's wording: *"This avoids manufacturing an empty measurement record merely so a `task_charge`
can possess an ID."*

### 2.3 Why the measurement cannot be the identity-bearing record

The ticket's implied direction — measurement canonical, posting hanging off it — fails on three
independent grounds, and the first is fatal on its own:

1. **A `task_charge` has no measurements.** If the measurement were the identity-bearing record, a
   fixed-price Charge could not have an id at all without fabricating a measurement shell for it.
2. **It assigns the canonical identity to the half we explicitly intend to delete.** Either the public
   event vanishes when measurements prune, or the measurement shell must survive forever — which
   defeats the split it was performed to enable.
3. **Nothing that keys on the identity depends on measurements.** Refunds, wallet movements,
   corrections, invoice references, the Charge projection, the Pricing Receipt and economic analytics
   are all economic concepts. Re-pointing all four correction paths and the public `event_id` to serve
   readers that do not exist is cost with no purchaser.

---

## 3. Retention is the load-bearing reason, and it is the only one

### 3.1 Three candidate justifications were put; exactly one was banked

The grilling put three reasons and an explicit "none of these hold" option. Only **retention clocks**
was selected. That matters for how this document is written: the other two are real *consequences* of
the split and are recorded as such, but neither is load-bearing and neither would have justified it
alone.

| Candidate reason | Status |
|---|---|
| **Two retention clocks** | **load-bearing** — §3.2 |
| The empty half on `task_charge` rows | consequence, and the argument for *direction* (§2.3) — not for splitting at all |
| Measurement is write-once, economics resolve later | **not banked** — #155 §6 already models this within one row as `FROZEN` vs `RESOLVE_ONCE` |

The third deserves the explicit "no": *different change times* looks like a reason to split, and it is
not, because #155 already solved it. `provider_cost_micros` going from `NULL` to a value weeks later
is `RESOLVE_ONCE`, enforced at the database with a trigger backstop. Splitting the row would not
improve that by one line. Recorded so a later reader does not re-derive it as a fresh argument.

### 3.2 Two published clocks cannot honestly share one row

Two merged decisions each published a retention promise, and they disagree by years:

- **#148 §11** — Pricing Receipts are retained **six years**, as a *published* promise, deliberately
  diverging from ADR-0004's reasoning because *"a receipt is the highest-volume record in the system"*.
- **#153 §12.4** — bulky measurement detail prunes at a **shorter** horizon, and the receipt must
  therefore retain the quantities and rates it used so *"the money stays explicable after the
  measurements expire"*.

As one row, honouring both means a housekeeping job runs `UPDATE` against the durable economic record
to blank a column. As two rows, it means `DELETE FROM posting_measurement`, and the posting is never
written to at all.

### 3.3 What pruning-by-mutation costs #155, in #155's own terms

This is the decisive form of the argument, and it is the owner's:

> *[One row] requires retention jobs to mutate the durable posting merely to prune analytical payloads.
> That weakens the otherwise clear controlled-mutation rules.*

#155 §6 exists because *"immutability today means the `save()` door is locked and the queryset door is
open, with one writer already walking through it"*, and its remedy is that **every column declares one
permitted transition, enforced at the database**. `PRUNABLE` is the one class in that table that
authorises a *destructive* write to a six-year economic record, performed by a scheduled job, on the
highest-volume table in the system. It is also the only class whose legality depends on a *cross-field*
condition: #153 §12.4 forbids pruning the measurements of a still-`unresolved` record, because
remediation needs them. So a `PRUNABLE` column is a permitted destructive mutation whose permission
depends on the value of a different column on the same row.

Removing the measurements to their own table deletes that class outright. That is the purchase.

---

## 4. This amends #155 §6.3 — `PRUNABLE` leaves the posting

The transition-class table becomes three classes on the posting and one whole-record rule on the child:

| Class | Permitted transition | Examples |
|---|---|---|
| **FROZEN** | none after insert | `id`, `tenant_id`, `customer_id`, `task_id`, `event_type_id`, `kind`, `effective_at`, `created_at`, `currency`, `charge_id`, idempotency identity |
| **RESOLVE_ONCE** | unresolved/`NULL` → one terminal value, exactly once; then frozen | `provider_cost_micros`, `billed_cost_micros`, `costing_status`, `pricing_status`, unresolved receipt sections |
| **SET_ONCE** | `NULL` → value, once | `stop_context` |
| ~~PRUNABLE~~ | — | **removed from the posting** |

`PostingMeasurement` is governed as a **whole record**, not per column:

```
INSERT   once, in the same transaction as its posting
UPDATE   never — no column of a measurement record is ever rewritten
DELETE   permitted only at or after prunable_at,
         and only while the parent posting is not unresolved
```

Three consequences worth stating:

1. **The child needs no transition classes**, because it has no lifecycle — it is written once and
   later deleted. `UPDATE` being categorically prohibited is a simpler rule to enforce and to test than
   any per-column scheme.
2. **The posting's rules become uniformly non-destructive.** After this amendment, *nothing* deletes or
   blanks data on a posting, ever. That is a materially stronger sentence than #155 could write, and it
   is the sentence the six-year promise actually needs.
3. **#153 §12.4's unresolved exemption becomes a cross-table condition** on a `DELETE`, evaluated
   against the parent's `costing_status`/`pricing_status`. This is a deliberate coupling and must be
   tested: pruning a record whose posting is still `unresolved` silently breaks #146's remediation and
   #148 §7.3's completion, and does so on exactly the records that most need fixing.

---

## 5. Absence has two causes, so the record says which

### 5.1 The requirement

Volunteered by the owner rather than asked: once a measurement record can be *absent*, absence carries
two unrelated meanings — **it expired** and **it never existed**. The API must distinguish them.

```json
{
  "id": "evt_123",
  "kind": "metered_usage",
  "provider_cost_micros": 240000,
  "measurements_status": "pruned",
  "measurements": null
}
```

```json
{
  "kind": "task_charge",
  "measurements_status": "not_applicable",
  "measurements": null
}
```

`measurements_status ∈ available | pruned | not_applicable`.

### 5.2 This is the fourth application of one pattern

The map has now refused the same collapse four times, and it is worth naming as a pattern rather than
a coincidence, because it will be proposed a fifth time:

| Decision | The two facts one blank was carrying |
|---|---|
| #147 §7.1 | a waived `0` vs a deliberately-free `0` → `pricing_status` |
| #151 §8 | `not_applicable` for a fixed job vs for a metering-only tenant → `not_applicable_reason` |
| #153 §3.4 | revenue unknown (`null`) vs revenue zero → four revenue states |
| **#165 §5** | measurements **pruned** vs **never applicable** → `measurements_status` |

In every case the cheap implementation returns an empty value and lets the reader infer. In every case
the two causes have opposite consequences: a `pruned` measurement set was real and is gone (and its
money remains fully explicable via the receipt); a `not_applicable` one never existed and no amount of
looking will find it.

### 5.3 What it costs the public contract

`UsageEventDetailOut` (`api/v1/schemas.py:234-258`) declares `usage_metrics: dict = {}` — a
non-optional dict defaulting to empty, which is precisely the collapsed representation this forbids.
It becomes `measurements: Optional[dict]` plus the status. Noted here because it lands in the same
slice as two changes already owed by merged decisions on the same schema:
`provider_cost_micros: int` and `billed_cost_micros: int` are both declared **non-optional** today,
and #146 §4 and #147 §7.1 make both nullable.

---

## 6. The Pricing Receipt is what makes pruning safe

Pruning is only defensible because the money remains explicable without the pruned data. #153 §12.4
already made that a content requirement on the receipt; this decision **depends** on it, so it is
restated as a precondition rather than a cross-reference:

> The Pricing Receipt must retain the economic calculation inputs required to explain the monetary
> result — the quantities, rates, denominators and resulting components actually applied. Pruning the
> broader analytical payload must never make historical money inexplicable.

The consequence that follows, and which #153 did not need to state:

**The quantities exist in two places on purpose, and they are not two sources of truth.** The
measurement record holds what was *reported*; the receipt holds what was *used to compute an amount*.
They are usually equal and are not required to be — a `reported` costing method (#146) produces a
receipt with a supplier-supplied amount and no computed quantity path at all. #148 §3.2 refuses two
sources that must agree; this is not that, because **nothing ever reconciles them**: the receipt is
authoritative for money, the measurement record is authoritative for analytics, and no query subtracts
one from the other.

---

## 7. The Charge survives, and so does its projection

### 7.1 The ruling

**Keep both.** The ticket asks whether #139's `Charge` collapses into the posting now that postings are
first-class, on the grounds that #139 chose projection *specifically* because corrections key on a
usage-event id — and that if postings become first-class, that reason may dissolve.

The reason does not dissolve, because **the id never moved**. #139's premise is not weakened by this
decision; it is confirmed by it.

```
Charge — the commercial decision
  task, customer, amount, currency,
  pricing_receipt, idempotency identity, lifecycle
        |
        | 1 : 1
        v
Posting — the money rail
  charge_id UNIQUE, kind: task_charge, effective_at,
  economic attribution, projected amount and currency
```

> **The Charge explains money; the posting moves and counts it.**

### 7.2 Why one-to-one does not make one of them redundant

They answer different questions, and a 1:1 cardinality means *one commercial decision has exactly one
representation on the shared money rail* — not that one record is surplus.

| Ask the Charge | Ask the posting |
|---|---|
| Why does this customer owe £5? | How much has this customer spent this month? |
| Was this Charge retried or voided? | What entered the wallet or the invoice? |
| Which Pricing Book rule produced it? | What revenue belongs in this analytics bucket? |
| What refund or adjustment relates to it? | |

Collapsing them would make one record responsible for both *deciding* money (idempotency, pricing
decision, void/refund relationships, provenance) and *moving* it (aggregation, settlement rails,
reporting attribution).

### 7.3 The invariant, and why #153 already forbids the alternative

**No monetary consumer may read the `Charge` directly.** #153 §2.3 settled this from the analytics
side, and it is merged:

> Analytics keeps reading revenue off the projected posting, not off the `Charge` record. […]
> Introducing a second aggregation path over `Charge` rows would create two totals that can disagree —
> the shape #148 §3.2 refused outright.

Structural enforcement, extending #151 §11.2:

```
Posting.charge_id   unique; non-null when kind = task_charge
Charge              exactly one posting once committed
Creation            atomic, or an exactly-once outbox whose
                    incomplete state is detectable and repairable
Amount              copied from the Charge onto the posting,
                    never independently authored
```

**Refunds and adjustments follow the same shape**: their own canonical decision record, projected onto
the same rail — never a mutation of the original Charge and never a direct edit of a historical total.
This is the third unbuilt recovery surface #148 §17 flagged, and it now has a stated shape even though
it still has no owner (§13).

---

## 8. The one query that spans both halves

Exactly one read contract aggregates across the seam, and it has exactly one consumer.

`get_customer_usage_summary` (`apps/metering/queries.py:177-221`) sums `units` and
`billed_cost_micros` in a **single** grouped query, and is consumed only by `/me/usage-summary`
(`api/v1/me_endpoints.py:357-362`) — the end-customer portal.

```python
rows = (UsageEvent.objects.filter(...)
    .values("event_type").annotate(
        units_sum=Sum("units"), billed_sum=Sum("billed_cost_micros"),
        cnt=Count("id")))
```

Under the split this becomes a join. That is the honest, complete cost of the split on the read side —
one query, one endpoint, inside metering.

**But the sharper consequence is not the join.** `total_units` on that response now has a *shorter
life* than `total_billed_micros` on the same response. A customer looking at a period older than the
measurement horizon sees a real billed total beside a units figure that has expired. Under §5's rule
that must be stated, not rendered as zero — and today the code does exactly the opposite, which is
§10's first defect.

---

## 9. `units` — the column every prior pass missed

`UsageEvent.units` (`usage/models.py:22`) appears in **none** of #145's re-model, #153's analytics
realignment, or #154's migration matrix. #154 §11 lists `usage_metrics → measurements`, `tags →
deleted`, `dim1..dim6 → dim1..dim10` and `pricing_provenance → pricing_receipt`, and does not mention
`units` at all.

It is a legacy scalar quantity that predates #145's declared measurements, and #145 conceptually
replaced it: quantities now live as declared, named measurements, and the rate side gained
`amount_micros` + `per_quantity`. Yet `units` is still written at ingest, still summed in the read
contract above, and still exposed on two public schemas.

This document places it on the child record — where it plainly belongs, being a quantity — **but does
not settle whether it survives at all.** Two readings, both defensible:

1. **Redundant with `measurements`** — a scalar "how many" beside a declared map of named quantities is
   the same collapsed representation #145 deleted elsewhere; it should be retired and
   `/me/usage-summary` should report a declared measurement or a rollup instead.
2. **A deliberate rollup** — a single comparable magnitude across differently-shaped Event Types.
   #149 §11 warns that per-event counts stop being comparable across differently-granular Event Types;
   `units` has the same disease and #153 §5 already built the vocabulary (`rollup:`) for the honest
   version.

Recorded as residue with a recommendation for (1), because a magnitude that no rate reads and no
decision has defended is dead weight on the hottest path. **It must be settled inside slice 2**, since
it decides whether the child record has two columns or one.

---

## 10. Live defects found while deciding

Each is owed a test, per the repo's ratchet.

### 10.1 `queries.py:212` renders unknown as zero, on a customer-facing endpoint

```python
({"event_type": r["event_type"], "units": r["units_sum"] or 0,
  "billed_cost_micros": r["billed_sum"] or 0, "event_count": r["cnt"]}
```

Both `or 0` fallbacks are the defect this map has now killed four times. Under #147's nullable
`billed_cost_micros`, `billed_sum` is `NULL` when every event in a group has unknown revenue, and this
renders it as **£0.00** on `/me/usage-summary` — the *end customer's own* view. Under this decision,
`units_sum` acquires the identical problem once measurements prune.

**This is a different site from the one #150 already recorded.** #150 flagged
`metering/queries.py:232-237` (the Pool basis, which reads low and stops blocking). This is
`:207-212`, it is customer-facing, and it was not previously recorded. The docstring even documents the
behaviour as intended — *"NULL units sum as 0"* — which is how it survived.

### 10.2 `iter_billable_usage_events` is accidentally correct and undocumented

`queries.py:495-515` filters `billed_cost_micros__gt=0`. Under nullable revenue, SQL evaluates
`NULL > 0` as unknown, so unresolved-revenue events are silently excluded from invoicing. That happens
to be the **right** behaviour (#147 §7.3: no resolvable cost → no automatic customer liability), but it
is right by accident of three-valued logic, not by design, and nothing states it. A future author
"fixing" the filter to `COALESCE(billed_cost_micros, 0) > 0` would change nothing; one writing
`>= 0` would begin invoicing unknowns. Owed an explicit predicate and a test.

### 10.3 The public detail schema cannot express any of the new states

`UsageEventDetailOut` (`schemas.py:234-258`) declares `provider_cost_micros: int`,
`billed_cost_micros: int` and `usage_metrics: dict = {}` — three non-optional fields that #146, #147
and this document each make nullable. The schema is the contract; until it changes, the states exist in
the database and are unrepresentable on the wire. Grouped into one spec change in slice 4.

### 10.4 Restated, not re-found

#155 §14.3's finding stands and this decision narrows its blast radius: the `save()` guard does not
bind because `QuerySet.update()` bypasses it (`usage/models.py:103-106` vs
`usage_service.py:199-209`). With `PRUNABLE` removed from the posting (§4), the set of legitimate
queryset writers to a posting shrinks to resolution and `stop_context` — both of which #155 §6.4 already
requires to be conditional updates asserting exactly one affected row.

---

## 11. Names, assessed against ADR-0006

ADR-0006 is now the living authority, so every name below is assessed against its seven rules rather
than proposed freely.

| Name | Assessment |
|---|---|
| **`Posting`** (model, replacing `UsageEvent`) | **R2 — one canonical public term per concept.** See §11.1. |
| **`PostingMeasurement`** (model) | Repo convention is singular model names (`UsageEvent`, `Refund`, `WalletTransaction`, `RawIngestEvent`). Table `ubb_posting_measurement` under #154 §6.3's rule; **23 chars**, well inside Postgres's 63; **verified: no `ubb_posting*` table exists today**, so neither it nor `ubb_posting` collides with any of the 60 `db_table` declarations in the tree. |
| **`measurements_status`** | R1 — no unit suffix involved. Parallels `costing_status` and `pricing_status` exactly, which is the point: three statuses, one naming shape. |
| `available` / `pruned` / `not_applicable` | `not_applicable` deliberately reuses #148 §4.4's word for the same meaning — *this was never going to have one* — rather than coining a synonym. |
| **`prunable_at`** | R6 does not apply (not a configured maximum). It is a timestamp naming the moment a permission begins, matching `effective_at`/`recorded_at`. |

The owner's answer wrote `PostingMeasurements` (plural). Recommended singular, per the convention
above; flagged rather than silently changed.

### 11.1 `UsageEvent` is a live two-names-for-one-thing, and #154 missed it

Every decision document since #139 calls this record **the posting**. #153 §2.3, #151 §11, #155 §6.3
and #154 §3.8 itself all use that word in prose while the code says `UsageEvent`. That is exactly the
condition ADR-0006 R2 exists to remove — and #154 removed an identical one three fields away, ending
`pricing_provenance` / "receipt" / "audit trail" as three names for one record.

The name is also now simply wrong for one of its two kinds. #154 §3.8's own contract table says a
`task_charge` row does **not** represent a provider operation, is **excluded** from recorded event
counts, and carries no measurements. Calling that a "usage event" misdescribes it on all three counts.

**Recommendation: `UsageEvent` → `Posting`**, table `ubb_posting`. Noted as amending #154, whose
migration matrix renamed four fields on this model and left the model name unexamined. The owner's
answer uses `Posting` throughout, which this document treats as the ruling.

**The public path is a separate question and is not changed here.** `GET /metering/usage/{event_id}`
keeps its shape: `usage` is the product area, and the id still identifies exactly what it identified
before. Renaming the model does not oblige renaming the route, and #155's "no provisional public
vocabulary" rule is satisfied because nothing provisional ships. Flagged in §13 as the one place where
the internal and external nouns will differ.

---

## 12. What this constrains

- **#155 (migration & cutover)** — **§6.3's transition-class table is amended** (§4): `PRUNABLE` leaves
  the posting, and the child gains a whole-record rule with no `UPDATE` at all. The split lands in
  **slice 2** (measurement & catalogue), which is where the measurement re-model already sits; the
  posting's own columns are already scheduled across slices 3 and 4. **`units` must be settled inside
  slice 2** (§9). The two-way SDK gate and the disposition manifest are unaffected — no operation is
  added or removed.
- **#152 (console)** — inherits a **fifth** canonical fixture scenario. #155's six
  (`known_economics`, `unknown_cost`, `waived_revenue`, `pricing_not_applicable`, `incomplete_total`,
  `indeterminate_ceiling`) do not cover **`measurements_pruned`**, and under #155's governing rule —
  *a semantic state is not complete until one real consumer demonstrates its intended rendering* — it
  needs one. The named defect shape is `measurements ?? {}` rendering an expired payload as "no usage".
- **#156 / #157 (Code Builder)** — **nothing new to call.** The generator reads the Event Type's
  costing method (#151 §16) and emits one reporting call site (#149); the split changes neither. The
  generated code sends measurements exactly as it does today; that they are stored in a child record is
  invisible at the boundary.
- **#158 (end-to-end audit)** — gains two assertions with real money behind them: that a pruned
  measurement set never changes a historical COGS, revenue, margin or invoice figure, and that a
  posting whose status is `unresolved` cannot have its measurements pruned.
- **#153** — §12.4's obligation on the receipt is now a **precondition of this decision** (§6), not a
  cross-reference. If the receipt does not snapshot the quantities and rates it used, pruning is
  unsafe and the split must not ship.
- **#148** — §11's six-year floor now applies to a record that contains **no bulky payload at all**,
  which materially improves the storage question §17 flagged as *"never been multiplied out"*. The
  multiplication is now over the posting and its receipt only.
- **ADR-0006** — gains the `UsageEvent → Posting` rename (§11.1) and three enum values.
- **ADR-0007** — gains the amended transition-class table (§4).

---

## 13. Residue, flagged not buried

- **`units` is undecided** (§9) — placed on the child, recommended for retirement, settled by nobody.
  It is the only open item that changes the child record's shape, and it must close inside slice 2.
- **The measurement horizon has no number.** #153 §12.4 established that a shorter clock exists and
  #148 §11 fixed the long one at six years. **Nothing anywhere states what the short clock is** — 90
  days, 13 months and "one billing period plus a quarter" are all defensible and imply very different
  storage. `prunable_at` gives it a home; no decision gives it a value.
- **Who runs the prune, and is it reversible?** It is not — a deleted measurement record is gone. No
  decision states whether pruning is automatic at `prunable_at`, tenant-configurable, or operator-run,
  and #148 §17's *"who may run a remediation"* is now the second question of this shape with no owner.
- **The internal noun and the external path will differ** (§11.1). `Posting` in code,
  `/metering/usage/{event_id}` on the wire. Defensible and deliberate, but it is a new instance of the
  thing ADR-0006 R2 dislikes, and a future reader will ask.
- **Refund's `OneToOneField` survives unexamined.** This decision leaves it untouched because nothing
  here disturbs it — but *one refund per posting, forever* is a structural constraint on partial
  refunds that no decision in this map has ever argued for. It is inherited from before the map and
  should be argued once, not inherited twice.
- **The recovery surfaces are now four.** #148 §17 counted three unbuilt ones (#146's remediation
  queue, #147's adjustment, #148's remediation); §7.3 above adds the refund/adjustment-as-projected-
  decision shape. Four tickets have now each described a recovery mechanism and none owns building one.
- **The cross-table prune condition sits on the hottest table.** §4's rule — do not delete while the
  parent is `unresolved` — is a join or a denormalised flag on a bulk delete over the highest-volume
  table in the system. The mechanism is unspecified, and it is the same "DB enforcement mechanism is
  unspecified and sits on the hottest path" residue #155 already recorded, now with a second instance.
- **Two inserts per event on the write path.** One insert becomes two inside the same transaction
  (`usage_service.py:414` is the single site). #149 deleted the fast lane on the finding that real load
  is ~100 events/s against a documented ceiling of 100–300/s per instance — this decision spends some
  of that headroom, and nobody has measured how much.
