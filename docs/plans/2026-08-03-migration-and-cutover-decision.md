# Migration and cutover — eight complete slices, and the licence that pays for them

**Ticket:** [#155](https://github.com/ashcochrane/ubb/issues/155) · **Parent map:**
[#137](https://github.com/ashcochrane/ubb/issues/137) · **Date:** 2026-08-03 ·
**Decided against:** `main` @ `0cf00b5` (#154's vocabulary lock + ADR-0006)

**Status:** decided. This document is **frozen evidence** and the only home of the slice plan, the
per-slice contract and the cutover step. The rules that keep binding after cutover live in
[ADR-0007](../adr/0007-schema-and-contract-change-rules.md), which is the living authority.

---

## The decision in one paragraph

The re-model lands as **eight complete slices plus a cutover**, each one green on `main` across
every gate before the next begins — not a big bang, because the single reason a big bang would be
required (you cannot leave a database half-migrated) does not apply here: #153 §13 already ruled the
operational rows are destroyed, and **nothing is deployed**, so an intermediate state costs a
developer's local database rather than a customer's money. Migrations need not carry data *during*
the re-model and the 162 of them are **squashed at cutover**, from which point the data-carrying rule
binds hard. The word "immutable" leaves the posting: it becomes **economically protected with
controlled lifecycle mutations**, its columns declared into four transition classes enforced at the
database, because three merged decisions each require writing to a posting after it is created and
today's `save()` guard is already bypassed by design. Every slice records its own machine-generated
contract-break block while the gate runs cumulatively against `api-v1-launch`; the suppression file
clears only once a new baseline is tagged. The SDK gains an **operation-level** two-way gate in slice
0 and publishes as **v4.0.0** after slice 8. There is no meaningful rollback and the document says so:
**the back-out is the clean-break licence itself**, and admitting the first integrator becomes a
deliberate act gated on #158's audit rather than something that merely happens.

---

## 1. The ticket's premise, corrected

The ticket asks seven questions. Three findings changed what four of them mean.

### 1.1 Nothing is deployed

There is no Dockerfile, no infrastructure-as-code, no `fly.toml` / `render.yaml` / `Procfile`, and no
deployment step in `.github/workflows/ci.yml` — CI runs tests and gates and stops. The only database
configuration in the repository is `docker-compose.yml`, which brings up Postgres and Redis on host
ports 5433 and 6380 for local development. The owner confirmed the reading: UBB runs on developer
machines and nowhere else.

**Consequences, which run through the whole document:**

- **"Cutover" is a code event, not a data event.** There is no moment at which a running system
  switches models. There is the commit at which `main` reaches the new model.
- **#153 §13.5's "engineering-only backup" is a developer's `pg_dump`**, not an operations artifact,
  and should be described as such rather than implying a restore procedure that has no subject.
- **#153 §13.5's five assertions become tests in the suite**, not a runbook. A runbook has no operator.
- **"Existing data" means local development data.** The only durable artifact it has is
  `apps/platform/tenants/management/commands/seed_dev_data.py` (240 lines), which is rewritten, not
  migrated.

### 1.2 The console cannot be wedged — CI already forbids it

The ticket asks for an order of operations "so the console is never wedged between a spec change and
its own update". The repository already answers this, and the answer is structural rather than
procedural.

The `contract` job in `.github/workflows/ci.yml` runs on **one commit** and executes, in order:

| Step | What it proves |
|---|---|
| Drift gate | `scripts/export_openapi.py` regenerates `openapi/v1.json` with zero diff |
| SDK core regeneration gate | the committed `ubb/_core` is exactly what the pinned generator emits |
| SDK exception regeneration gate | `ubb/_exceptions_generated.py` matches `openapi/error-codes.json` |
| Breaking gate | `oasdiff` against the base spec, with the committed suppression files |
| UI contract snapshot gate | `pnpm ui:api:check` copies `openapi/v1.json` into the console and diffs |
| TypeScript smoke gate | the committed spec generates clean types |
| **UI typecheck** | `tsc -b` — **the console compiles against the freshly regenerated types** |
| UI tests | the console's own suite |

A spec change that is not matched by its console update is **red in the same commit**. The wedge the
ticket asks us to avoid is not reachable on a green build. The job's own comment records why the last
two steps exist: without them the app "drifted three contract changes behind the API (#129, #131,
#132) without anything going red".

**So there is no ordering to decide.** What the console owes each slice is a different question, and
§9 answers it.

### 1.3 The wedge lives in three artifacts nobody was gating

The protection in §1.2 covers the spec, the generated SDK core and the console's types. Three
artifacts sit outside it, and all three are already rotting:

**(a) The SDK's hand-written call surface.** Only `ubb/_core` rides the regeneration ratchet. The
hand shell is **115 public methods across 1,752 lines** (`metering.py` 427, `client.py` 680,
`billing.py` 281, `referrals.py` 178, `webhooks.py` 117, `subscriptions.py` 69) and **no gate ties it
to the spec**. Comparing every `/api/v1/...` literal in it against `openapi/v1.json` — 66 plain
literals plus 39 f-strings, 105 references in total — finds **three paths that exist in no spec and
no router**:

```
/api/v1/metering/pricing/rate-cards/{card_id}
/api/v1/metering/pricing/rate-cards/{card_id}/history
/api/v1/metering/pricing/rate-cards/batch
```

The first is the rate-retire route that the #86 final sweep re-nested under its book — its removal is
recorded in `openapi/oasdiff-err-ignore.txt` — and the SDK still calls it. The same comparison finds
**42 spec paths the SDK never calls at all**. #148 §15 found one of these; #154 §9.2 ordered "the two
dead-method deletions". The real number is three, and it took fifteen lines of script to find, which
is the point.

**(b) `ubb-platform/scripts/integration_test.py`.** 1,680 lines driving the full flow — customer
creation, top-up, usage, withdrawal, refund, tenant billing, subscriptions, referrals — against a
running server and real Stripe. It is **not in CI** (it needs a live server and the Stripe CLI) and
was **last touched in `5c9bcdf`, 2026-02-15**, the repository's first commit series. It has since
survived the #78 contract big bang, the #86 final sweep, the whole arch-deepening program and the
console rebuild without a single edit. It still calls `pre-check` five times — an endpoint #141
retires outright. It has been dead for roughly six months and nothing noticed, because nothing was
watching.

This matters more than its line count: the outstanding launch gate recorded across this program is
the **operator live Stripe money test**, and this is the artifact that would perform it.

**(c) The console's mock fixtures.** 2,963 lines across nine features. They are typed against the
generated types, so `tsc -b` stops them drifting in *shape* — but their content is hand-maintained
narrative. `dashboard/api/mock-data.ts` opens by explaining that every breakdown "sums exactly to
those totals so the page reads as one consistent business", and warns that two rosters are kept "in
sync by hand". **Every value in them is known.** §9 explains why that is now a gap rather than a
detail.

---

## 2. The shape of the break

### 2.1 The ruling

**A run of complete slices, each green on `main` across every gate before the next begins.**

### 2.2 Why not a big bang

The argument for a big bang is that a partially-migrated system is incoherent, so the transition must
be atomic. That argument is **unavailable here on two independent grounds**:

1. **There is nothing to preserve across intermediate states.** #153 §13.2 already ruled that usage
   and economic postings, Charges and receipts, Tasks and steps, wallet deductions, period
   accumulators, analytics snapshots and reconciliation state are all removed at cutover. A slice that
   leaves the old operational rows meaningless is not a hazard; it is the destination arriving early.
2. **Nothing is deployed** (§1.1). "Landing" a slice means merging to `main`. A partial state costs a
   developer a `dropdb` and a `migrate`.

The repository's own big-bang precedents are each **one surface**: #78 was the error model (RFC 9457 +
code registry + cursor envelope, "one PR"), #85 was one SDK release. Neither carried a domain re-model.
The genuinely comparable program is the arch-deepening set #109–#115 — seven interlocking refactors,
each merged green, in sequence.

The counter-argument, stated fairly: the decisions in this map interlock severely, so intermediate
states cost real thought. A held-open branch would need none. That cost is accepted, because the
alternative is the largest unreviewed diff in the repository's history, red for its entire life, with
no green checkpoint to bisect against.

### 2.3 The build targets the reconciled end state, not the ticket sequence

This is a rule, not an observation. The decisions **narrow and reverse each other**:

- #145 §7.3 **reversed seven of #142's eight** currency-column deletions, on a different rule
  (*owns an amount?* rather than *can it differ?*).
- #147 §7.3 **narrowed #146 §9.4 one day after it merged** — unresolved events do not bill next period
  on the revenue side.
- #147 §6.1 **narrowed #138**, removing Event Category from the pricing ladder the entity was created
  to serve.
- #151 §13 **narrowed #139 §3.3**, moving the priced-step refusal from the start gate to declaration
  time.
- #153 §12.4 **extended #148 §4**, making measurement quantities non-optional on the receipt.

Building ticket-by-ticket would build things and then unbuild them. **The build reads the decision
documents together, with ADR-0006 as the naming authority**, and implements the reconciled state.

### 2.4 Expand/contract is explicitly rejected

The standard zero-downtime technique — add the new structure alongside the old, migrate behaviour,
then delete the old — is the obvious third option and is **refused**, because it *is* the dual-model
state #153 §13.5 already forbade: "No legacy operational data and no dual-read behaviour enters the
new system." Expand/contract buys continuity for a running system. There is no running system.

---

## 3. The slice plan

Nine steps. Each is a vertical: model → service → API → spec → SDK → console for one concept.

| # | Slice | Carries |
|---|---|---|
| **0** | **Gates and money primitives** | #154's enforcement gates installed, seeded with today's violations as allowlists that may only shrink; the SDK operation gate (§8); the cumulative oasdiff comparison (§7.3); `core/money.py` collapsing #142's 20 minor-unit sites across 11 files; the `apps.platform.tasks` → `apps.platform.work` module move (#154 §3.1) |
| **1** | **Demolition** | #149's fast lane in full — the ingest endpoint, `RawIngestEvent`, the settle sweep, estimate-and-hold, the `metering_async` flag, ops ingest-health; `scripts/integration_test.py` (§11.4) |
| **2** | **Measurement and catalogue** | Event Type as a real entity, Provider, declared measurements (`value_type`, `unit`, `required_for_costing`, `source_path`), Measurement Concept, ten Grouping Field slots with the six per-slot indexes dropped, Event Category as analytics-only, `tags` folded into `metadata` |
| **3** | **Cost** | Effective-dated Cost Rates, `costing_method ∈ {calculated, reported}`, `costing_status`, nullable `provider_cost_micros`, the one shared bound, quarantine for unplaceable events; deletion of `require_cost_card_coverage`, the `cost_coverage_required` refusal, `Unpriceable` and all three `PricingError` raise sites |
| **4** | **Price** | Pricing rules with `pricing_method ∈ {margin_over_cost, direct_event_price}`, the Pricing Book, immutable Pricing Book Publish records, forward-only scheduling, remediation, Pricing Receipts (`receipt_schema_version` separate from `pricing_engine_version`), nullable `billed_cost_micros` with four `pricing_status` values and `not_applicable_reason`; deletion of `TenantMarkup`, `Plan.markup_percentage_micros`, `Plan.fixed_uplift_micros` |
| **5** | **Work** | Six lifecycle states, caller-supplied `idempotency_key` with permanent claim, required close `outcome` + reason pair, `Charge` and its 1:1 projection onto one marked posting, `/api/v1/tasks` as a top-level ungated mount with the three prefix moves, declared granularity, the silence and absolute deadlines |
| **6** | **Spend control** | The four families — Ceiling, Customer Spend Pool, Wallet policy, Admission control — with ceilings COGS-denominated and time-or-cost based, at-or-above comparison everywhere, `uncapped: true` declaration, utilisation as information; deletion of `max_concurrent_requests` |
| **7** | **Analytics** | One economic analytics query, the five-endpoint collapse, per-measure status, `field:`/`rollup:` grouping with its discovery contract, the two retention horizons; deletion of `Customer.revenue_mode` and the `/revenue-mode` and `/customers/{id}/revenue` pairs |
| **8** | **Cutover** | §11 |

### 3.1 Why this order and not another

**Not by product.** ADR-001's four products look like natural boundaries and are the wrong ones. The
moment metering's revenue becomes nullable, two readers in *other* products break in the same commit:
`apps/metering/queries.py:235-236` returns `agg["billed"] or 0`, which silently reads unknown revenue
as zero and makes a Pool read low; and `apps/billing/handlers.py:31` evaluates
`if billed_cost_micros > 0` — which becomes `None > 0`, a `TypeError`, **inside the drawdown handler**.
A metering-only slice cannot be green. The slices are domain verticals precisely because the domain
cuts across the products.

**Not by layer.** A model-only slice cannot merge: the drift gate would demand a spec regeneration the
API layer has not made, and `tsc -b` would compile the console against it.

**Demolition early.** The fast lane is pulled to slice 1 because it is **pure removal with no
successor** — #149 established that the estimate *is* the price, that spend control loses nothing, and
that the lane's own accuracy advantage had already evaporated. Removing it first means every later
slice has one ingest lane to change instead of two. The deletions that *do* have successors
(the coverage gate, `TenantMarkup`, `max_concurrent_requests`) stay in the slice that replaces them,
which is what keeps §2.4's no-dual-read rule true at every commit.

**#154's renames distributed, not front-loaded.** Landing the whole vocabulary lock as slice one is
tempting and wasteful: #154 §6.2 itself records that the `Rate`/`RateCard` table inversion "resolves
by construction", because #138 splits `Rate` and #148 replaces `RateCard` and both tables are rebuilt
regardless. Renaming a table that slice 4 deletes is work with no product. What *does* go to slice 0
is the module move (it touches everything, so it wants to be early) and **every gate**, because a gate
installed before the code complies is what makes the vocabulary impossible to regress.

### 3.2 The seeded-allowlist ratchet

Slice 0 installs #154 §12's gates **while the codebase still violates them**, each seeded with a
literal list of today's violations. Every later slice deletes entries; no slice may add one. The
allowlists reach zero at slice 8.

This is the repository's existing pattern rather than a new invention — the SDK core regeneration
gate, the spec drift gate and #115's pagination ratchet all work by making the current state the
floor. It converts eight slices of vocabulary discipline from a review burden into a mechanical one.

**This mechanism is not the API suppression file, and §7.4 explains why the two cannot be described
together.**

---

## 4. The per-slice contract

A slice is complete when **all** of the following hold on the commit that lands it. This list is the
definition of "green" referred to throughout.

1. `python manage.py check` passes and `makemigrations --check --dry-run` is clean.
2. The platform suite and the SDK suite pass.
3. `scripts/export_openapi.py` regenerates `openapi/v1.json` with zero diff.
4. The SDK's generated core and exception hierarchy regenerate with zero diff.
5. `oasdiff` passes with the slice's own reviewed break block added (§7).
6. The SDK operation gate passes and the disposition manifest is accurate (§8).
7. `pnpm ui:api:check`, `tsc -b` and the console suite pass, with the slice's rendering assertions
   added where it introduced an economic state (§9).
8. Every allowlist the slice was able to shrink has been shrunk, and none has grown.

**No provisional public vocabulary.** Anything a slice adds to `openapi/v1.json` ships under its
**final** name and final contract, even where the implementation behind it is only partly built.
A slice must not expose a temporary public shape merely because part of its internals has landed —
otherwise a later slice must break the contract a second time solely to repair the first break's
placeholder. Internal scaffolding is permitted; public scaffolding is not.

---

## 5. Existing data, and the migration rule

### 5.1 The question is not about today's data

Migration `0028_remove_usageevent_idx_usage_attribution_and_more.py` implements the
`product_id`/`service_id`/`agent_id` → `dim1`/`dim2`/`dim3` move as `AddField` + `RemoveField` rather
than `RenameField`, and ADR-0005's Migration note warns that replaying it against populated tables
loses the data. `apps/platform/tasks/migrations/0004_the_clean_cut_run_to_task.py` faced the same
freedom and chose the opposite technique — `RenameModel`, `AlterModelTable`, `RenameField` — with the
header *"Plain rename migrations — no live tenant exists, so there are no data concerns."*

Two precedents, same licence, opposite techniques. With nothing deployed, **both work today**. The
question is therefore not "what does this data need" but **"what does this repository teach, and what
binds once it stops being free?"**

### 5.2 "Always carry the data" is not well-defined for this re-model

This is a re-model, not a rename. When `Rate` splits into Cost Rates and pricing rules with different
resolution semantics, when `RateCard` is replaced by the Pricing Book, when `TenantMarkup` is deleted
outright and `Customer.revenue_mode` with it, there is no `RenameField` that expresses the change.
A blanket "carry the data" rule would be inapplicable to most of the work it governs.

### 5.3 The ruling

**During the re-model, migrations need not carry data.** The operational rows are destroyed by
decision (#153 §13.2) and nothing is deployed; preserving them is work with no beneficiary.

**At slice 8 the 162 migrations are squashed** to a fresh initial migration set describing the new
model only.

**From that point the rule binds hard, in ADR-0007:** a migration that renames or moves a column
carries its data, by `RenameField` or by an explicit `RunPython`, and dropping a populated column
requires a stated reason. The rule is backed by a check rather than a note, on the repository's own
convention that hard rules are backed by tests.

### 5.4 What the squash buys, beyond tidiness

**It sharpens #154's most important gate.** §14 of the vocabulary lock warns that the forbidden-term
search "will have false positives in vendored code, **migration files carrying historical column
names**, and the frozen dated documents", and that "an over-broad exclusion silently disarms it."
Squashing deletes that entire exclusion category: the retired vocabulary stops existing in the tree
rather than being excused by a filter. The exclusion list and the seeded allowlists reach zero
together.

**It is the third of a matched set at slice 8** — migrations squashed, audit ledger reset (#154 §4.2),
suppression file cleared (§7.5). All three are the same act: history that describes a superseded model
stops being carried as if it described the live one.

### 5.5 What this dissolves, said out loud rather than dropped

**#154 §6.3 required `ubb_customer_sub_item` → `ubb_customer_subscription_item` to be a genuine table
rename** preserving rows, primary keys, foreign keys, indexes, constraints and sequences, explicitly
"not a drop and recreate". Under a squash there is no prior table to rename — the initial migration
creates `ubb_customer_subscription_item` directly. The requirement is **dissolved, not forgotten**,
and its underlying intent survives in ADR-0007's rule, which is what it was protecting.

### 5.6 What survives the reset

#153 §13.3's rule stands: configuration survives **only where it maps cleanly and validates**;
anything requiring inference or carrying obsolete meaning is recreated or discarded. With nothing
deployed, the concrete subject of that rule is exactly one artifact: **`seed_dev_data.py`**, rewritten
at slice 8 rather than migrated. It hardcodes `--billing-mode` choices `meter_only|prepaid|postpaid`,
which #154 renames to `customer_billing_mode ∈ {external, prepaid, postpaid}`, so it cannot survive
untouched in any case.

Event Types and measurements are **explicitly re-declared** under the new contracts, never inferred
from historical traffic (#153 §13.3).

---

## 6. The posting's lifecycle — four transition classes

### 6.1 The ticket's question dissolves; a live one replaces it

The ticket asks whether historical rows get a read-time translation layer or whether reporting accepts
a discontinuity date. **Neither**: #153 §13 removes the rows, so there is no history to translate.
And §5.3's squash makes the removal mechanically trivial — the table is dropped and recreated by the
initial migration, so **no row is ever deleted** and `UsageEvent.delete()`'s guard
(`apps/metering/usage/models.py:108-109`) is never challenged. A `TRUNCATE` is not needed either.

The live question underneath is different, and three merged decisions force it:

- **#146** — completing an unresolved blank is explicitly *not* a correction; *"the nullable column is
  what buys in-place resolution"*. A null cost becomes a real cost, in place, possibly weeks later.
- **#153 §12.4** — bulky measurement detail prunes at its horizon while the receipt lives six years.
  Pruning is an in-place removal.
- **Today, already** — `stop_context`.

Meanwhile #146 requires corrections to be entries *beside* the original and #148 makes the receipt an
immutable authoritative record. "Immutable" has to mean something more precise than it does.

### 6.2 The live defect: the guard does not bind

`UsageEvent.save()` raises `ValueError` on any non-adding save
(`apps/metering/usage/models.py:103-106`). It is bypassed **by design**, and the code says so —
`apps/metering/usage/services/usage_service.py:199-209`:

```python
def _tag_stop_context(event, **builder_kwargs):
    """...The write is a queryset update — the model save() guard keeps the
    event immutable to everything else — inside the caller's recording
    transaction, so the row is never visible untagged..."""
    ...
    UsageEvent.objects.filter(id=event.id).update(stop_context=ctx)
```

`QuerySet.update()` does not call `save()`. So immutability today means *the `save()` door is locked
and the queryset door is open, with one writer already walking through it*. It is a convention
enforced by nobody at the database level — and the new model needs at least three more writers.

### 6.3 The ruling

**The posting is described as "economically protected with controlled lifecycle mutations", never as
"immutable".** Every column is declared into one of four transition classes, and **the database
enforces the permitted transition** so that every door obeys the same rule.

| Class | Permitted transition | Examples |
|---|---|---|
| **FROZEN** | none after insert | `id`, `tenant_id`, `customer_id`, `task_id`, `event_type_id`, `kind`, `effective_at`, `created_at`, `currency`, idempotency identity |
| **RESOLVE_ONCE** | unresolved/`NULL` → one terminal value, exactly once; then frozen | `provider_cost_micros`, `billed_cost_micros`, `costing_status`, `pricing_status`, unresolved receipt sections |
| **SET_ONCE** | `NULL` → value, once | `stop_context` |
| **PRUNABLE** | populated → `NULL`/pruned marker, after the declared horizon only | measurement payload |

### 6.4 RESOLVE_ONCE, precisely

`NULL` and `0` must remain distinguishable at the database level: `NULL` is *not resolved*, `0` is
*resolved as exactly zero* — which #147 §4.3 already made a real and distinct fact. The status and its
amount **transition atomically**. Application code performs resolution as a conditional update
asserting exactly one affected row:

```sql
UPDATE ...
   SET provider_cost_micros = %s, costing_status = 'known'
 WHERE id = %s
   AND provider_cost_micros IS NULL
   AND costing_status = 'unresolved'
```

A **database trigger is the backstop**, so another writer cannot bypass the transition rule regardless
of the path taken. Once a real value has been written it can never be replaced by a different value —
which is exactly #146's distinction between *completing a blank* and *overwriting an assertion*, now
expressed in the schema instead of in prose.

### 6.5 SET_ONCE, and why it is not "append-only"

`stop_context` is a single JSON column written once. Calling it append-only would invite the
implementation that rewrites the list on each write — under which **two concurrent writers overwrite
each other**, silently. So: if one annotation suffices, it is SET_ONCE. **If several independent
annotations must be preserved, they become separate append-only child records** —
`PostingStopContext(posting_id, reason_code, trigger_source, recorded_at)` — never a repeatedly
rewritten array on the posting.

### 6.6 PRUNABLE, and what pruning may never touch

Pruning removes detail; it never rewrites history. A pruned column may not be repopulated with
different historical content, and pruning may **never** change resolved COGS, customer revenue, the
economic statuses, the currency, the canonical attribution, or the receipt inputs needed to explain
the monetary result. #153 §12.4's obligation is what makes this safe: the receipt retains the
quantities and rates actually used, so the money stays explicable after the measurements expire.

### 6.7 This amends #148

#148 made the Pricing Receipt immutable. That is now stated precisely:

> A Pricing Receipt is immutable **except for the one-time completion of fields explicitly recorded as
> unresolved**. Once those fields resolve, the receipt is **sealed**.

- unresolved blank → real value — **permitted once**, and not a correction
- known value → different known value — **prohibited**; it must be a separate correction or adjustment
  record beside the original

This preserves the distinction already established across #146 and #147: **resolution completes
previously unknown information; correction changes a value that was already asserted.**

### 6.8 Enforcement, in two layers

Both layers, for different purposes. **The service layer** gives clear commands, validation, friendly
errors and the conditional atomic update. **The database** rejects forbidden `OLD → NEW` transitions
regardless of `save()`, `QuerySet.update()`, admin scripts, management commands or jobs.

Tests must attempt **every prohibited transition through both ORM update paths and through direct
SQL**. A guard that only one of the three doors respects is what §6.2 already found.

---

## 7. The spec gates

### 7.1 What the launch tag actually marks

The `api-v1-launch` tag was cut on `ac6ca81`, 2026-07-22. The re-model breaks essentially the whole
surface beneath it, which looks like a problem until you read `docs/api-compatibility.md`, which
already anticipated the case:

> **The existence of the tag is not, by itself, the thing that binds; a consumer depending on the
> contract is.**

No consumer arrived. The launch tag marks a contract nobody consumed, and #137 constraint 1 —
reaffirmed independently by #148 §11.3, #153 §13.4 and #154 §14 — licenses this break.

There is also a working precedent for entries *below* the boundary: #132's **"PRE-LIVE LANE"** block,
which states in the file that it is "not a deprecation", names the `api-v1-launch` status, and points
at the compatibility page's dated note "which also names the day the note is deleted".

### 7.2 The ruling

**Each slice records its own reviewed contract-break block.** For every slice after slice 0:

1. Complete the slice's implementation.
2. Regenerate OpenAPI from the code.
3. Run `oasdiff`.
4. **Generate the break entries mechanically.**
5. Review and accept only the breaks that slice introduced.
6. Merge only when the whole repository is green.

**The detected changes must never be written by hand.** #132's own file header records what happened
last time: hand-derivation put seven WARN-level lines in the ERR file, "where `--err-ignore` silently
did nothing for them", and missed two ERR findings entirely — corrected only "by installing oasdiff
and running it for real instead of hand-deriving the entry list".

A reviewed block **may** carry human metadata — slice, date, PR, decision-document references, and the
reason the break is accepted. It may not carry a hand-typed finding.

### 7.3 Two comparisons, doing two jobs

- **Authoring** a slice's new entries uses `previous main → proposed slice`, so a slice does not
  re-derive every earlier entry.
- **The gate** validates the complete accepted break set using `api-v1-launch → proposed slice`, so
  every cumulative break is proven to have been reviewed.

This is a **change to today's CI**, which compares only against the base branch or `HEAD^`. Installing
the cumulative comparison is a slice-0 build item.

### 7.4 The two mechanisms must not be conflated

This document originally described "the allowlist reaching zero at cutover" as covering both. It does
not, and the distinction is load-bearing:

| | Implementation-rule allowlists | API-break suppressions |
|---|---|---|
| **Seeded with** | today's violations of #154's gates and the SDK gate | nothing; they accumulate |
| **Direction** | shrink every slice | grow as intentional breaks land |
| **At slice 8** | **zero** | **still populated** |
| **Why** | the violations are defects being repaired | the differences from `api-v1-launch` are real and intentional |

The suppression file **cannot** be empty while CI still compares against `api-v1-launch`. Emptying it
requires changing what it is compared against.

### 7.5 After slice 8

1. Tag the completed re-model commit as the **new immutable API baseline**.
2. Point CI at that baseline.
3. Reset the active suppression file to empty.
4. Run `oasdiff` again and confirm there are **no unexplained differences**.

`api-v1-launch` **remains immutable** as the historical marker — it is not moved or deleted. The
per-slice blocks stay available in git history and in this document; they simply stop being active
suppressions once the comparison baseline changes.

---

## 8. The SDK

### 8.1 The version is nearly forced

ADR-003 §6 states an SDK major happens exactly "when the SDK's own surface breaks", and
`ubb-sdk/tests/test_release.py` pins 3.0.0 with the comment *"This ticket IS the v3.0 cut — the single
coordinated breaking release."* A second clean cut is **v4.0.0**, published **after slice 8** — not per
slice. The repository stays internally coherent throughout; the public release is one event.

### 8.2 The ruling: an operation-level, two-way gate, installed in slice 0

Code review demonstrably does not catch this — §1.3 found three calls to nonexistent routes sitting
green in CI. Two separate properties get enforced.

**(1) Every hand-written SDK call must target a real API operation.** The check validates the complete
operation identity — **HTTP method + normalised path**, or preferably the OpenAPI `operationId`. A
path match alone is insufficient: `GET /api/v1/tasks/{task_id}` must not be treated as equivalent to
`POST /api/v1/tasks/{task_id}`.

The three existing invalid calls seed a slice-0 allowlist. That allowlist **only shrinks and must
reach zero before cutover**. After slice 0, no new unmatched call may merge.

**(2) Every OpenAPI operation must carry an explicit SDK disposition.** A generated manifest classifies
each committed operation as one of:

- **`wrapped`** — exposed through the hand-written ergonomic SDK
- **`generated_only`** — reachable through the generated client surface, with no ergonomic wrapper
- **`not_yet_wrapped`** — deliberately unavailable through the current SDK surface

Today's **42 unwrapped operations** seed the manifest. That number **need not reach zero for v4.0.0**,
but it must stay **visible and mechanically accurate**, and any increase must be an explicit reviewed
change rather than an accidental omission.

### 8.3 Route literals stop being duplicated

The strongest long-term shape is a hand-written method that **references a generated operation or an
operation registry**, rather than carrying another raw `"/api/v1/..."` string. Raw route literals are
either prohibited in the hand-written layer or confined to **one mechanically checked registry**, so
that a route rename cannot leave a stale SDK string behind — which is precisely how all three dead
calls survived.

### 8.4 Per-slice behaviour

Each relevant slice: implement → regenerate OpenAPI and the generated SDK components → run the forward
SDK → OpenAPI operation check → regenerate the coverage manifest → update the affected ergonomic
wrappers → merge green.

At slice 8: invalid-call exceptions zero, manifest accurate, contract and SDK tests green → publish
v4.0.0.

### 8.5 The tests that pin it

At minimum CI must prove:

1. a nonexistent SDK route **fails**
2. a valid path with the **wrong HTTP method fails**
3. a renamed OpenAPI operation with a stale wrapper **fails**
4. a new OpenAPI operation absent from the coverage manifest **fails**
5. an explicitly `generated_only` or `not_yet_wrapped` operation **passes and remains visible**
6. a correctly mapped ergonomic wrapper **passes**

### 8.6 Why the hand shell is not simply deleted

Deleting it and shipping only the generated core plus thin ergonomics would give the strongest
possible guarantee. It is rejected as **unnecessarily destructive**: #144's research verified that the
pinned generator produces response DTOs only and no usable call surface, so the ergonomics would have
to be rebuilt from scratch inside an already substantial re-model — and #156/#157 target this SDK, so
its shape is not free to churn. The ergonomic layer has product value; the missing thing was a
mechanical invariant behind the review, not a different architecture.

---

## 9. The console

### 9.1 The obligation is not "keep it compiling"

§1.2 established that CI already guarantees that. What CI does **not** guarantee is that the console
tells the truth about a number it does not know — and three merged decisions each warn about exactly
that failure:

- **#147** — margin *unavailable* must never render as 0%
- **#150** — `indeterminate` must never render as "under limit"
- **#153** — every measure carries a status; a partial total must not present as a total

None of those is checkable today, because every value in all 2,963 lines of fixtures is known. The
distinction between `£0.00`, unknown, not applicable, waived, incomplete and indeterminate **is now
part of the economic contract**, and TypeScript proves only that the console can *receive* those
states.

The defects the types cannot catch are ordinary and easy to write:

```ts
const displayed = amount ?? 0;
status === "unknown" ? "0%" : formatMargin(...)
```

### 9.2 The ruling, with a proportionality rule

**Any slice that introduces or changes an economic state must add at least one representative fixture
and at least one rendering assertion for that state.** A slice that only moves a module or renames an
internal table owes nothing, unless the visible contract changes. This is not ceremony applied to
every slice.

The contract each assertion protects:

| State | Renders as | Never as |
|---|---|---|
| known zero | `$0.00` | — |
| unknown amount | *Unknown* / *unavailable* | `$0.00` |
| incomplete total | *At least $4.20* | `$4.20` presented as final |
| indeterminate ceiling | *Indeterminate* | "under limit" |
| `not_applicable` pricing | *Not applicable* | `$0.00` revenue |
| waived revenue | `$0.00`, **explicitly waived** | an unlabelled zero |

### 9.3 Where the obligation falls

| Slice | Fixture | Assertion |
|---|---|---|
| 3 Cost | unresolved supplier cost | renders *Unknown*, not `$0.00` |
| 4 Price | unknown, waived and `not_applicable` revenue | three distinct renderings |
| 6 Spend control | indeterminate ceiling | not labelled "under limit" |
| 7 Analytics | incomplete aggregate | lower-bound language plus status |

### 9.4 Canonical scenarios, not fixture sprawl

Copying whole page responses nine times is how nine files come to describe the same state
differently — the risk the existing fixtures already flag when they warn that two rosters are kept "in
sync by hand". Instead, a small set of canonical economic scenarios is defined once:

```
known_economics · unknown_cost · waived_revenue
pricing_not_applicable · incomplete_total · indeterminate_ceiling
```

Feature fixtures are **composed** from them:

```ts
makeUsageAnalyticsFixture({
  cost: unresolvedCost(),
  revenue: knownRevenue(500_000),
});
```

The **shared formatters and status components** carry focused unit tests; each relevant page carries
**one integration-level assertion** proving it uses them. That keeps the cost incremental rather than
letting fixture volume grow with every slice.

### 9.5 The governing rule

> **A semantic state is not complete until one real consumer demonstrates its intended rendering.**

---

## 10. Rollback, and the licence

### 10.1 There is no meaningful revert, and saying so is the honest answer

With nothing deployed there is no data to restore and no service to roll back. `git revert` works
mechanically and is useless past the first couple of slices, because every later slice builds on
earlier ones — slice 4's pricing rules cannot be reverted once slice 5's Charges depend on them.

Per-slice revert plans were considered and rejected as **largely fiction**: eight documented back-outs
that would not survive contact cost more than they protect. A parallel old-model branch was rejected
because it *is* the dual-model state #153 §13.5 forbade, and it would rot immediately since nothing
runs against it.

### 10.2 What can actually be lost is the freedom to be wrong cheaply

#148 §11.3, #153 §13.4 and #154 §14 each say independently that the clean-break licence is spent once
and **expires at the first integrator**. So:

- **While no integrator exists**, a decision that turns out wrong is corrected by another free break —
  the same mechanism this re-model is using.
- **After one lands**, the same correction costs an ADR-003 §4 cycle: `deprecated: true`, a `Sunset`
  header, a changelog entry, an email, and 90 days.

**The back-out is the licence.** That is the whole of it.

### 10.3 The licence closes on a deliberate, gated act

The repository already makes this possible: **no API route creates a tenant.** The spec's `/tenant/*`
paths all operate on an existing tenant, and the only way one comes into existence is the
`seed_dev_data` management command. Admission is already a human act — it cannot happen by accident.

So it is made an explicit gate: **the first integrator is admitted deliberately, conditioned on
#158's audit passing.** Until then, `docs/api-compatibility.md`'s dated status note stays in place and
ADR-003 §4 does not yet govern. The note's own instruction — "Delete this note the day the first
tenant goes live" — becomes the marker for the act rather than a passive observation.

The real risk this names is not "the migration fails". It is **"we let someone in before we were
sure"**, and that is a decision with an owner rather than an accident with a cause.

---

## 11. The cutover step

Slice 8 is the one step that cannot be sliced further. It is a code event (§1.1), and it consists of:

### 11.1 The three resets

1. **Migration squash** (§5.3) — 162 migrations become a fresh initial set describing the new model.
2. **Audit-ledger reset** (#154 §4.2) — rename surviving actions, delete registrations for dead
   concepts, drop pre-cutover rows, open with `system.preproduction_model_cutover`. ADR-004 §2's
   additive-only rule and retention floor apply unchanged from that entry onward.
3. **Suppression-file reset** (§7.5) — after the new baseline tag is cut and CI repointed.

### 11.2 The rewrites

- **`seed_dev_data.py`** — rewritten under the new model, not migrated (§5.6).
- **`CLAUDE.md`** — #154 §9.3's restatement.
- **`docs/api-compatibility.md`** — repointed at the new baseline tag, dated note retained (§10.3).
- **Living docs** — ADR-0005 superseded where #145 and #154 already record it; `CONTEXT.md` glossaries
  per product; `docs/conventions/` where a rule landed there.

### 11.3 The assertions

#153 §13.5's five, **as tests in the suite** rather than a runbook:

1. no old posting contributes to a balance or a report
2. no undeclared measurement survives
3. no legacy pricing provenance is read
4. every new event validates against its Event Type
5. every new monetary record uses the new receipt shape

Plus this document's own: **every seeded allowlist is at zero**, the SDK invalid-call list is at zero,
and `oasdiff` against the new baseline reports no unexplained difference.

### 11.4 The end-to-end proof

**`ubb-platform/scripts/integration_test.py` is deleted in slice 1**, with the demolition. Dead code
claiming to be a safety net is worse than no safety net, and §1.3 established it has been dead for six
months. #158 exists specifically to design the end-to-end audit; #155 does not invent a third
mechanism beside it and the existing `ubb-platform/conformance/` suite.

**The obligation is not deleted with the script.** Recorded explicitly so it cannot vanish during a
cleanup:

> **Slice 8 is not complete until a live Stripe money test has actually been run**, in whatever form
> #158 specifies.

The `conformance/` suite (schemathesis, fuzzing the app in-process against the committed spec) stays
**non-gating** — CI's own comment says "Promoting this to a gate is a separate future decision", and
that decision belongs to #158, not here.

### 11.5 The engineering backup

#153 §13.5's one-time snapshot is **a developer's `pg_dump`**, taken for forensic reference. It is
explicitly **not a supported product data source** and must not influence the new application model.
With nothing deployed it has no operational role, and describing it as one would imply a restore
procedure with no subject.

---

## 12. Sequencing — the remaining decision tickets

**All remaining map decisions are settled before slice 0.** #165, #152, #156, #157 and #158 close, and
only then does the build begin.

**The owner ruled this over my recommendation to interleave.** My proposal was to run each ticket at
the point the build first needs it — #156 before slice 2 because it decides what the catalogue must
enumerate, #152 before slice 5 because task states otherwise have no console consumer and §9.5's rule
would be unmeetable, #158 before slice 8, #157 after. The owner's ruling is the more consistent one
with #137's charter, which has been planning-only throughout: **the decision phase closes completely,
then the build starts.**

**#165 in particular is settled first** for reasons that survive either ordering: the break is
available once, and splitting the busiest table afterwards would re-touch the **26 non-test files
across all five products** that read `billed_cost_micros` (billing 8, metering 6, subscriptions 6,
platform 5, referrals 1) and re-point the four correction paths that key on a usage-event **identity**
rather than a value — `Refund.usage_event` (a `OneToOneField`), the `usage_deduction:{id}` exactly-once
drawdown key, `WalletTransaction.usage_event_id`, and `get_usage_event_cost`. It also keeps the public
`event_id` — a path parameter on `GET /api/v1/metering/usage/{event_id}` — identifying one stable
thing from cutover onward.

**The cost is recorded in §17:** #152 and #157 are prototype tickets and will now design against a
model that exists only on paper, which is the specific hazard #144's research named.

---

## 13. Live defects found while deciding

Each is owed a test.

1. **The `UsageEvent` immutability guard does not bind.** `save()` raises
   (`apps/metering/usage/models.py:103-106`) but `QuerySet.update()` bypasses it, and
   `usage_service.py:199-209` uses that bypass deliberately, with a docstring asserting the guard
   "keeps the event immutable to everything else". It does not. Resolved by §6.
2. **Three SDK methods call routes that do not exist** — `rate-cards/{card_id}`,
   `rate-cards/{card_id}/history`, `rate-cards/batch` — none in `openapi/v1.json`, none in any router.
   The first was retired by the #86 final sweep, whose removal is recorded in the err-ignore file.
   All three are green in CI because their tests patch `httpx.Client`. #148 §15 found one; #154 §9.2
   ordered two deletions; the number is three. Resolved by §8.
3. **The only end-to-end money test has been dead for six months.**
   `ubb-platform/scripts/integration_test.py`, last touched `5c9bcdf` on 2026-02-15, still calls a
   retired `pre-check` endpoint five times, and is in no CI job. Resolved by §11.4.
4. **`apps/metering/queries.py:235-236` silently reads unknown revenue as zero** (`agg["billed"] or 0`)
   — already flagged by #150, restated here because it is the reason a product-ordered slice cannot be
   green (§3.1).
5. **`apps/billing/handlers.py:31` evaluates `if billed_cost_micros > 0`** inside the drawdown handler
   — becomes `None > 0` and raises the moment #147's nullable revenue lands. Also #150's find; the
   same point.
6. **Two migration precedents in the same repository teach opposite techniques under the same
   licence** — `usage/0028` (AddField+RemoveField) and `tasks/0004_the_clean_cut_run_to_task`
   (RenameModel/RenameField). Resolved by §5 and ADR-0007.

---

## 14. What this decision changes in merged documents

| Document | Change |
|---|---|
| **#148 §4** | **Amended.** A Pricing Receipt is immutable *except* for one-time completion of fields recorded as unresolved, then sealed (§6.7) |
| **#146** | **Extended.** "Completing a blank is not a correction" gains a database-enforced shape: `NULL` → one terminal value, exactly once, `NULL` distinguishable from `0`, trigger as backstop (§6.4) |
| **#153 §13** | **Executed and narrowed.** The reset is a code event; the backup is a `pg_dump`; the five assertions are tests. The removal needs no delete path because the squash drops the tables (§6.1, §11) |
| **#154 §6.3** | **Dissolved, deliberately.** The `ubb_customer_sub_item` true-rename requirement has no subject after the squash; its intent survives as ADR-0007's rule (§5.5) |
| **#154 §12** | **Extended.** The gates install in slice 0 seeded with today's violations, as allowlists that may only shrink (§3.2) |
| **#154 §14** | **Discharged in part.** The migration-file exclusion that "silently disarms" the forbidden-term search stops existing at the squash (§5.4) |
| **ADR-003 §5** | **Read, not changed.** The launch tag marks a contract nobody consumed; `docs/api-compatibility.md`'s own sentence settles it (§7.1) |
| **ADR-0005 Migration note** | **Superseded.** Its warning becomes ADR-0007's rule with a check behind it (§5.3) |

---

## 15. Answers to the ticket's seven questions

**1. One cut or several?**
**Several — eight complete slices plus a cutover** (§2, §3). The reason a big bang would be required
is unavailable twice over: #153 already destroys the operational data, and nothing is deployed. The
repository's big-bang precedents (#78, #85) were each one surface; the comparable program (#109–#115)
ran sequenced. Slices are **domain verticals**, never products or layers, because nullable revenue in
metering breaks billing's drawdown handler in the same commit.

**2. Must this re-model's migrations carry data, and what is the rule?**
**Not during the re-model; the rule binds from cutover** (§5). The operational rows are destroyed by
decision and nothing is deployed, so carrying them serves no one — and "always carry the data" is not
even well-defined for a re-model in which most columns have no successor. At slice 8 the 162
migrations are squashed, which additionally deletes the exclusion category that would have blunted
#154's forbidden-term search. From that point ADR-0007 binds: a rename or move carries its data, and
dropping a populated column requires a stated reason.

**3. Translation layer for historical rows, or a discontinuity date?**
**Neither — the rows do not survive** (§6.1), and the squash means they are never deleted either;
the tables are dropped and recreated, so `UsageEvent.delete()`'s guard is never reached. The real
question underneath — what "immutable" means when three merged decisions require writing to a posting
after creation — is answered by **four declared transition classes enforced at the database** (§6),
with the posting described as *economically protected with controlled lifecycle mutations*.

**4. What does the suppression entry say, and who signs it off?**
**One machine-generated block per slice, signed off by the owner at that slice's PR** (§7). Entries
come from running `oasdiff`, never from hand-derivation — #132's header records that hand-derivation
put seven WARN lines where `--err-ignore` ignored them and missed two ERR findings. Human metadata
(slice, date, PR, decision refs, reason) is permitted; hand-typed findings are not. Authoring compares
`previous main → slice`; the gate compares `api-v1-launch → slice`, which is a CI change and a slice-0
item. **The suppression file cannot reach zero** while that baseline stands — it clears only after
slice 8 tags a new one.

**5. Does the SDK ride this as a major, and what version?**
**Yes — v4.0.0, published after slice 8** (§8), which ADR-003 §6 makes near-automatic. The substantive
answer is the gate: an **operation-level** two-way check installed in slice 0 — every hand-written call
resolves to a real operation (method + path, ideally `operationId`), and every operation carries an
explicit disposition (`wrapped` / `generated_only` / `not_yet_wrapped`). Three invalid calls seed an
allowlist that reaches zero before cutover; 42 unwrapped operations seed a manifest that need not.
Route literals move into one checked registry.

**6. What order keeps the console from being wedged?**
**The question is already answered by CI** (§1.2) — the `contract` job ends in `tsc -b` and the console
suite on the same commit as the spec, so the wedge is unreachable. What each slice owes instead is
**honesty about unknown numbers** (§9): any slice introducing an economic state adds a representative
fixture and a rendering assertion, composed from six canonical scenarios rather than duplicated across
nine fixture files. A semantic state is not complete until one real consumer demonstrates its
rendering.

**7. What is the back-out if the new model is wrong?**
**There is no meaningful revert, and the document says so** (§10). What can be lost is the freedom to
be wrong cheaply, which three merged documents agree expires at the first integrator. So the back-out
**is** the licence: while none exists, a wrong decision is fixed by another free break; afterwards it
costs an ADR-003 §4 cycle. Admitting the first integrator therefore becomes a **deliberate act gated
on #158's audit** — which the repository already supports, because no route creates a tenant.

---

## 16. Constraints this imposes on other tickets

- **#165 (split the posting)** — decides **before slice 0**, and its answer rides this break. Whatever
  it rules, §6's four transition classes apply to whichever row carries the economic columns, and the
  four identity-keyed correction paths must each name the half they point at.
- **#152 (task dashboard)** — decides before slice 0, and its output must satisfy §9.5: the task
  lifecycle states and the indeterminate ceiling need a consumer that demonstrates their rendering, and
  tasks have no console surface today.
- **#156 (Code Builder inputs)** — decides before slice 0; what it requires to be **enumerable** is a
  direct constraint on slice 2's catalogue, since #144 named the missing registry as the hard blocker.
- **#157 (Code Builder output)** — generated code must use only final vocabulary (#154 §13) and must
  target operations that pass §8's gate; §4's no-provisional-vocabulary rule is what makes that stable.
- **#158 (end-to-end audit)** — inherits the deleted integration script's obligation (§11.4), owns the
  live Stripe money test that slice 8's completion depends on, owns whether `conformance/` is promoted
  to a gate, and owns the audit that §10.3's admission gate is conditioned on.
- **#137 (the map)** — constraint 1 is exercised here for the last time, at the same cutover #148 §11,
  #153 §13.4 and #154 §14 already invoked. This document closes the map's "Not yet specified" item
  *"the sequenced handoff plan itself"* and narrows *"how far the Python SDK surface must change"*.

---

## 17. Residue, flagged not buried

- **#152 and #157 will prototype against a paper model.** §12's ordering means both prototype tickets
  design surfaces for states that do not exist in code yet. #144's research named this hazard for the
  Code Builder specifically. The mitigation available is that both are cheap, throwaway artifacts by
  charter — but a prototype that cannot be run against anything is weaker evidence than one that can.
- **The cumulative oasdiff comparison is unbuilt and unproven.** §7.3 asks CI to compare against a
  tag rather than a base branch across eight slices of wholesale change. Nobody has run
  `oasdiff api-v1-launch → HEAD` on this repository yet, and the suppression file's size at slice 7 is
  unknown. If it becomes unmanageable, the fallback is per-slice comparison only — which loses the
  cumulative proof, and that trade should be made deliberately rather than discovered.
- **The database enforcement mechanism for §6 is unspecified.** Triggers, `CHECK` constraints and
  rules have different costs on the hottest insert path in the system, and #142 §8 already established
  that this path is throughput-sensitive. Which mechanism, and what it costs per insert, is an
  implementation decision this document does not make.
- **The `PostingStopContext` child table is conditional and undesigned.** §6.5 specifies it only if
  several independent annotations must be preserved. Whether they must is a #150/#165 question that
  nobody has answered.
- **42 unwrapped SDK operations is a product gap nobody has examined.** §8.2 makes it visible and
  explicitly does not require closing it. Somebody should eventually ask whether the SDK is missing
  something integrators need, rather than treating the manifest as a permanent shrug.
- **The seeded allowlists have no stated owner per entry.** §3.2 says they only shrink, but nothing
  says which slice is responsible for which entry, so an entry could survive to slice 8 by everyone
  assuming somebody else owned it. The slice plan implies most assignments; it does not record them.
- **Nothing decides what happens if a slice is discovered to be wrong two slices later.** §10 answers
  the question for the model as a whole, but not for the sequence — reverting slice 4 after slice 6 has
  landed is exactly the case §10.1 says is unavailable, and the answer "roll forward" is asserted
  rather than demonstrated.
- **`conformance/` remains non-gating throughout.** The schemathesis sweep will find contradictions
  between the implementation and the spec on every slice, and none of them will turn a PR red. That is
  the existing deliberate choice; it is worth noticing that the re-model is exactly when it would be
  most useful, and #158 owns whether to change it.
