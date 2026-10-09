# ADR-0019: A stop acknowledgement says how the stop was applied and what it was measured on, and a replay answers from what it said

**Status:** accepted
**Date:** 2026-10-09
**Decision records:** #569 — the preparation (comment `6066575387`: the table, the persistence
design, the replay pins), the owner's and consultant's rulings applied (`6069593729`), and the
final confirmation recorded in the issue body's "Current authority (2026-10-08)" section · the
owner's review of #611 (2026-10-09), which settled how the assessment runs on a report the live
debit does not count, that the line whose figures are frozen is internal, and that #609's two
"Before #569" pins are inverted · #609, whose precedence this freezes
**Companion:** ADR-0014 is the four families and the one compare this reports on; ADR-0007 §3 is
why every name below is final on the day it ships; ADR-001 is the boundary the billing facts cross

## Context

#179 §1.3 decided what the stop signal carries "so nothing is lost by catching it": beside the
event, the key, the scope and the reason, a **trigger source**, **what has been spent** and **what
it was measured against** — so that "a handler can log what happened without a follow-up read".
Its §8 called `trigger_source` a new field on the signal. On `main` before this ADR the
acknowledgement carried `stop`, `stop_reason` and `stop_scope` and nothing else of that list: no
mechanism, no bound, and for a customer-wide stop no amount at all.

A second gap sat under the first. An idempotent replay did not answer what the original said. It
re-read the customer's stop flag NOW, so a report first acknowledged unstopped could replay as
stopped and a stopped one as clear; it lost the unit's verdict entirely, so a ceiling crossing
replayed as `stop: false`; and it re-read the unit's ceiling assessment as it stood now. Adding a
bound and a measured amount to that replay would have published three more figures reconstructed
from facts that had moved.

Nothing that existed could be the authority for "what the acknowledgement said". The posting is
not the authority for where a stop came from (the owner's ruling); the signal ledger holds one row
per owner and line and overwrites it each episode; a unit's stop metadata is mutable; and the
kill announcements are deleted after thirty days.

## Decision

### 1. Three fields, final, on every acknowledgement

`RecordUsageResponse`, every batch item and `UBBStopRequested` (as properties over its `result`)
carry, after `stop_scope` and before the ceiling assessment:

| Field | Type | Meaning |
|---|---|---|
| `trigger_source` | string, nullable | The mechanism that applied the stop — the registry's open `trigger_source`, with its concept marker. Never the cause, which is `stop_reason`. |
| `stop_bound_micros` | signed integer, nullable | The monetary bound `stop_reason` names, as it stood when the stop was established. |
| `stop_measured_micros` | signed integer, nullable | The amount measured against that bound at that moment. |

All three are **required keys whose values may be null** — in the schema's `required` list, in
the contract and in the generated SDK model, with no default (the owner's review of #612). Null
means "this fact does not apply"; a missing key would be a third state, the server not sending
what it promised, and the contract leaves none. A rejected batch item recorded nothing and carries
all three as null. The older stop trio beside them keeps its own posture; this ruling is about
these three. A figure that does not apply is **null, never 0**; a real zero floor is `0`. Both
figures are **signed**: a hard floor's bound and the balance measured against it sit at or below
zero, so no minimum constrains either anywhere. `stop_reason` says what the figures mean economically, so there is no "amount kind"
field. The names are the confirmed ones (§A of the rulings): *bound* is the glossary's word across
all three families ("which bound was reached"), and "stop line" was not broadened to cover a unit
ceiling to make a name fit.

### 2. What the figures are

| `stop_reason` | `trigger_source` | `stop_scope` | bound | measured | stops when |
|---|---|---|---|---|---|
| `task_cogs_ceiling` | `usage_ingest` | `task` / `subtask` (widest wins) | the governing unit's pinned COGS ceiling | its supplier cost (COGS) total at the crossing | measured ≥ bound |
| `customer_spend_pool` | the episode's opener | `customer` | the Pool's stop line (`cap × hard_stop_pct ÷ 100`) of the customer whose Pool it is | that customer's month-to-date billed charges at the crossing | measured ≥ bound |
| `hard_floor` | the episode's opener | `customer` | the floor as a balance, `−min_balance_micros` (`0` is real) | the wallet balance at the crossing | measured < bound |
| `task_not_active` | null | the unit's own | null | null | — |
| (no stop) | null | null | null | null | — |

The figures follow the scope: a `task`-scoped stop on contained work's report carries its
**parent's** ceiling and rolled-up total, off the accumulate verdict (`reasons.CeilingCrossing`,
never a re-read of the row). For a customer-wide stop that was already standing when a report
arrived, the figures are **the episode's opening facts** — never today's counter, Pool or
configuration. Precedence is unchanged: a unit verdict takes the scalar slot over a customer-wide
one, and among customer-wide stops #609's order holds (the billing owner's line over a pooled
seat's own).

`task_not_active` names no bound — a stop reason is "which bound was reached" and this is the one
verdict that is not a bound — and no mechanism applied a stop on that report, so all three are
null. It stays out of the reason registry, deliberately; the acknowledgement's `stop_reason`
description now publishes that it can carry it.

### 3. The mechanism is the lane that applied the stop

| Lane | `trigger_source` |
|---|---|
| A unit's ceiling crossed by this recording | `usage_ingest` |
| A customer-wide episode opened by the recording's live debit | `usage_ingest` |
| …by the durable drawdown of a **usage report's** posting (the wallet floor, or either Pool level) | `usage_ingest` |
| …by the hourly reconcile passes, the reconcile a maintenance-switch flip enqueues, or the seat-level beat | `enforcement_patrol` |
| …by the durable drawdown of a delivered fixed-price unit's **Charge** posting | `charge_projection` (new) |

`charge_projection` is one mechanism value, never a reason, with no per-branch variants. The
`usage.recorded` payload deliberately carries no discriminator, so the drawdown handler reads the
posting's `kind` through metering's read contract (`get_posting_kind`). That drawdown is the path
that applies a fixed-price Charge's customer-wide stop: the projection writes one posting and emits
the same payload, which the handler draws down against the wallet floor and counts into the
customer's own Pool level; the live debit never sees it. `usage_drawdown` was proposed and
withdrawn — a report's drawdown is still a usage report's.

### 4. A recording keeps what its acknowledgement said

`StopAcknowledgement` (metering, beside the posting) is written for **every** posting the
recording path writes — `stop` true or false, the single route and every batch item — in the
recording's own savepoint, after the live debit that decides it. It holds the stop facts, the
ceiling assessment, the named unit's parent, and which unit (`stop_task_id`) or whose
customer-wide line (`stop_customer_id`) the stop was about. That identity is **internal**: two
Pool stops read alike at both levels, and the record is what says whose figures were frozen; no
public field publishes it.

Its rule is insert-only — `UPDATE` never, `DELETE` only as a sandbox's postings are discarded —
held by a `BEFORE UPDATE OR DELETE` trigger across every door (migration `usage.0045`), with
model guards beside it that are not the enforcement.

### 5. A replay reads that record and nothing else

For every field in §4, a replay answers from the record — never the live flag, the unit of work,
a Pool, configuration, a counter or `Posting.stop_context`. Cost and price facts stay read off the
posting row, as before; the unit totals stay null ("they say what THIS recording did"). A
recording-path posting with no record is an invariant violation, raised by name
(`StopAcknowledgementMissing`) and never reconstructed. A report sent under the key a Charge's
posting holds is refused before anything is admitted (`KeyHeldByACharge`, a 422), so the replay
can never answer from a posting that acknowledged nothing.

### 6. An episode records how it opened, and the facts ride the flag

The winning stop transition stamps the episode's `trigger_source`, bound and measured amount on
the signal ledger row beside `control_id` (every `drive_stop` caller states all three — required
keywords). The same facts ride the fast flag **as one value with the word** (compact JSON), so a
recording that reads another recording's flag before that transaction commits already hears how
the episode opened, and a reader can never see a word without its facts. `ensure_stop_flag` and
the re-point after a line lifts set the flag from the ledger's open row; a live debit that sets an
absent flag but loses the drive to an episode already open re-aligns the flag to that episode's
facts. And where a flag names a line but carries other facts than the ledger's open episode on it
— written on a failure path, by a lane whose drive raised — `ensure_stop_flag` re-aligns them the
next time a durable lane finds the episode open: the ledger owns how an episode opened. A bare
word (planted by the test door) reads with no facts.

### 7. Every report hears the standing stop

A report the live debit does not count — no resolved price, a zero one, or a postpaid report
back-dated into an earlier month — still runs the standing-stop read (the billing owner's flag and
a pooled seat's own, in the one MGET #609 built), and so does a debit that failed part-way. Its
acknowledgement is kept and replayed, so "not stopped" for a stopped customer would otherwise be
permanent. A blind read is still not-stopped (fail-open), and that is what is kept.

### 8. The batch item is typed

`UsageBatchResponse.results` is a list of `UsageBatchItemResponse`, which inherits
`RecordUsageResponse` field for field and adds `accepted`, `code` and `detail`. One schema, not a
`oneOf`: an OpenAPI discriminator must be a string property, and `accepted` is a boolean. A
rejected item carries `accepted: false`, `code`, `detail`, `stop: false` and every stop fact null.

## Departures from frozen decisions

CLAUDE.md's ratchet requires a departure to name the document and section, quote it, and state the
evidence. Two are made here; the evidence for both is the owner's and consultant's ruling of
2026-10-08 (`6069593729`, confirmed in #569's "Current authority"): *"Replay reads that snapshot
only. It must never reconstruct historical stop state from current counters, Task state, Pool
state, configuration, Posting, or the current live-stop record"*, with the consequences confirmed
explicitly — *"A replay of an event that originally returned stop=false continues to return that
original answer even if the customer or Task became stopped afterwards"* and *"A replay of an
event that originally returned a stop returns the original trigger/reason/scope/line/measured
values even if all of those live facts have since changed."*

1. **The Tier-2 real-time spend-control design**
   (`docs/plans/2026-06-19-tier2-realtime-spend-control-design.md`), §2: *"Every
   `record_usage` response — *including the idempotent-replay paths* — carries a `stop` verdict
   read from that flag."* And its invariant **I4**: *"`_result()` populates the stop fields on the
   happy path **and both idempotent-replay returns** … A replayed event for a stopped owner must
   not report 'all clear.'"* A replay now carries the verdict the ORIGINAL read, kept at the time;
   a replayed event whose original said "not stopped" says so still. What I4 protected — a caller
   that keeps working learns of the stop — is now carried by the caller's next new report and the
   start gate, both of which read the stop as it stands.
2. **#452** (slice 6 §3; merged as `64c341d2`): *"DECISION, revised on review: an idempotent
   REPLAY carries the unit's standing NOW, on `stop`'s own footing (the durable flag is read at
   replay time)"*, pinned by `test_a_replayed_acknowledgement_carries_the_units_standing_now`. The
   ceiling assessment is stop state derived from the unit, so a replay now carries the original's;
   the pin is inverted at its own address (`test_a_replayed_acknowledgement_carries_the_original_assessment`).

## Consequences

- **A retry of a lost acknowledgement no longer tells the caller of a stop that began after the
  original.** Confirmed knowingly; the next new report does, and so does the start gate.
- **The recording path writes one more row per recorded result** (a batch of 100, one hundred),
  inside the savepoint it already holds. The replay pays no extra query: the record rides the
  replay's one lookup (`select_related`).
- **`read_live_stop` is gone.** Its only caller was the replay; the live verdict is read once, by
  the recording that is acknowledged.
- **The flag's raw value changed shape** (word → word with its opening facts), which the live
  counter's own pin test now freezes.
- **#609's "Before #569" pins are inverted, not preserved**: the tipping report replays
  unstopped, and a stopped report replays stopped with its figures after the stop clears.
- **Known limitation.** When a lane's ledger drive RAISES (not loses), the flag it set carries
  that lane's own crossing facts — or none, where the flag was set by `ensure_stop_flag` with no
  episode open — until the next durable-lane pass opens the episode and re-aligns the flag to
  the ledger (§6; the hourly reconcile at the latest). Acknowledgements recorded in that window
  keep what they said, because a replay never re-reads: on that failure path a kept record can
  name the crossing that set the flag, or name the stop with null facts.
