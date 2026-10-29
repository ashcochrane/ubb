# ADR-0020: A quantity is exact text, a negative price is unknown with its reason, and a total is the sum of what resolved

**Status:** accepted
**Date:** 2026-10-20
**Decision records:** #603 — the owner's rulings (comment `6069675803`), the inspection of what the
authoritative records can carry (`6070096734`), the two questions ruled on 2026-10-20 (`6279554922`:
Q1, a negative customer price; Q2, the lower bound) and the owner's confirmation and amendments
(`6279966961`: the ceiling assessment against the enforcement trigger, `pricing_status_reason`
required and nullable, receipt schema 2 and renderer contract 3 mandatory) · #584 — a declared
constant rendered on both targets, whose temporary refusal this removes
**Companion:** ADR-0014 is the ceiling this re-reads (§7); ADR-0015 §3 is the renderer contract that
moves to 3 (§8); ADR-0016 and ADR-0017 are the two targets that carry a quantity as text; ADR-0013
§3 and ADR-0010 are the rails and the recovery figures §5 and §6 amend; ADR-0007 §5 is the pre-live
lane the published changes travel in

## Context

A Measurement quantity reached UBB as a JSON number and was held as one. The wire typed it
`dict[str, int]`, refused a negative, and was read by the standard library's JSON parser — so a
caller's `2.0` and `"2"` were both admitted by Pydantic's lax integer, a whole number past 2⁵³ came
back as a different integer, and a fraction had no way in at all. Costing multiplied that integer
by a rate and rounded each line "half-up". The rounding formula was `(n + d // 2) // d`, which on a
negative numerator sends an exact half toward +∞, not "up" in magnitude; no negative could reach it,
so the difference was never seen.

#571 had already declared a `constant` Measurement's value as exact decimal TEXT, in one canonical
grammar, because every numeric way of holding it loses something on the way to somebody. A recorded
quantity was the one place the same value still travelled as a number. #603 closes that, and the
owner's rulings settle what follows from letting a quantity be fractional, negative and of any
length: what a negative amount means on each money record, what a total over unresolved amounts can
honestly promise, and what a ceiling may conclude while something is unresolved. #584 is the
Code Builder's half: a declared constant could not be rendered while a quantity had no exact form a
generated file could send, so the Blueprint refused it (`constant_measurement_not_renderable`).

## Decision

### 1. A quantity travels as exact decimal text, and UBB canonicalises it on admission

A quantity is transported as exact decimal text. UBB canonicalises an admitted value before
persistence; stored quantities, receipts and read surfaces use the canonical text. No binary
floating-point conversion occurs.

The two grammars are #571's, for a constant's declared value, applied unchanged to a recorded one
(`apps/platform/event_types/exact_decimals.py`):

- **What a caller may send** — the single and batch recording routes and Verify's record — is any
  ACCEPTED spelling: base-10 ASCII digits, an optional leading `-`, an optional fractional part with
  a digit on each side of the point, and nothing else (no exponent, no `+`, no whitespace,
  separators or locale formatting). Leading zeros and trailing fractional zeros are spellings, not
  errors: `"01.50"` is admitted.
- **What UBB holds and answers** is the CANONICAL text admission makes of it, by editing the text so
  the value is never a number on the way (`"01.50"` is `"1.5"`, `"12.0"` is `"12"`, `"-0"` is
  `"0"`): what `PostingMeasurement` stores, what the acknowledgement echoes, what the event detail
  read publishes, what a receipt holds (§3), and what a recovery reason and a resolution run read
  back.

The server is the canonicalisation authority, and no client is required to send byte-identical
spellings: the SDK happens to canonicalise before it sends, and the shell target sends an accepted
spelling exactly as it was passed (§8). Both reach the same exact value.

- **A JSON number is refused, even a whole one.** The wire's value type is a string with the
  grammar's pattern; `2` is a 422 naming the quantity, as `"2.5x"` is.
- **The declared value type decides a fraction.** An `integer` Measurement requires a whole value
  (`"3.0"` is whole, and is held as `3`); a `decimal` one permits a fraction. A key no publication
  declares is held as its canonical text and leaves the cost unresolved, as before.
- **A negative quantity is valid, and zero is a real known value** — never missing, never
  discarded.
- **No precision or scale cap.** The grammar has no length bound and no binary float sits anywhere
  on the path: not on the wire, not in storage, not in costing, not in the SDK or either generated
  target. A batch item that breaks its own declaration is refused alone; a body the grammar cannot
  read at all is refused whole, as every malformed body is.

### 2. Arithmetic is exact; an exact tie goes away from zero; the money bound is refused by name

Costing reads canonical text as exact integers (`exact_parts`: sign, digits, scale) and multiplies
and divides once, so a fraction times a rate is exact up to the one division by the rule's
`unit_quantity` and the scale. That division rounds to the nearest whole micro and **an exact
half-micro tie rounds AWAY FROM ZERO** (`core.money.round_charge`). Every result that is zero or
positive comes out exactly as the old formula gave it; only an exact negative tie moves, toward −∞
rather than +∞. A margin over a cost uses the same rule. A fixed per-event component is added to the
line as declared, whatever the quantity's sign: a negative quantity never turns a fixed fee into a
credit.

The only bound is the money columns' own — a signed 64-bit integer of micros. An amount past it is
not a rounding question, it has nowhere to go: costing refuses it by name
(`AmountPastTheMoneyBound`, naming the quantity as written) as a validation failure, so the single
route answers 422 and a batch refuses that one item and records the rest. A long quantity on a rule
of nothing is an exact zero, never an overflow.

### 3. Receipt schema 2, and pricing engine 2.2.0

A receipt's component holds the quantity under `receipts.QUANTITY_KEY`. Schema 1 holds it as a whole
NUMBER; **schema 2** (`CANONICAL_QUANTITY_SCHEMA_VERSION`) holds it as the canonical text of §1.
`RECEIPT_SCHEMA_VERSION` is 2: a writer emits schema 2 and nothing else. `READABLE_SCHEMA_VERSIONS`
is `{0, 1, 2}` and every reader dispatches on all three — in particular `recorded_quantities`, which
feeds recovery, answers the same exact bag for a schema-1 and a schema-2 receipt of the same event.
The version, not the value's type, says what the quantity IS, so v1 was not kept on the ground that
a tolerant reader could take both spellings. An older receipt is read and never rewritten or
upgraded. The boundary refuses a schema-2 receipt holding a number, and a schema-1 receipt holding
anything but a whole number.

`PRICING_ENGINE_VERSION` moves **2.1.0 → 2.2.0**, a minor version. The receipt module's own rule
says the engine version moves when an amount would come out differently: an exact negative tie, a
fixed component on a negative quantity, a negative final price and an amount past the bound all now
come out differently. Every input that was legal under 2.1.0 — a whole, non-negative quantity —
computes exactly the amount it did, so nothing about the earlier receipts is disowned, which is what
a major version would claim.

### 4. `pricing_status_reason`: required, nullable, closed

A new closed public concept beside `pricing_status`, never a fifth status. Its one canonical value is
`negative_price_unsupported` — "UBB calculated a negative customer price but cannot authoritatively
carry it". `null` means no specific published reason applies.

- **Required and nullable on every surface that publishes `pricing_status`**: the acknowledgement,
  the batch item (accepted and rejected), the event detail read and list row, the unresolved queue
  row, the itemised event row and the supplied-revenue window. The key is always present; there is
  no third "absent" state and no default. Only a historical receipt may predate it.
  `test_the_price_status_reason_is_required_and_nullable.py` holds the census of publishers.
- **`unknown` is reworded to the truth**: no authoritative customer price is recorded for this
  event. The reason tells missing input apart from a result the current money rails cannot carry.
- **The computed negative number is published nowhere as a price.** It is kept internally exactly
  long enough to decide the status.
- **Not retried.** A resolution or repricing run does not select it — the calculation succeeded and
  configuration is not what is missing — and the working list a run is aimed at does not show it
  (`resolution_run.NOT_RETRIED`). A future negative-money capability selects these records
  explicitly.
- **Counted among the amounts not included.** It is an `unknown` price, so every unpriced count
  that carries the pair's unresolved status counts it.
- **Kept as provenance**: the reason rides the receipt's `pricing.detail` (an additive detail key,
  exempt from the schema rule; the receipt moves to schema 2 anyway, for §3) and the usage-recorded
  outbox payload, beside the posting's own column.

### 5. The negative-economics boundary of v1

A negative amount is calculated exactly, then persisted where the authoritative records can carry it
faithfully, and otherwise recorded with its economic resolution unresolved and an explicit reason —
never clamped, dropped or marked known. **The sign is decided on the posting's total, not per
component**: components that cancel are a known zero, and a negative whole is negative though one
component is positive.

- **A negative known supplier cost (COGS) is representable** (`6070096734`): it is `known`, with no
  new reason, and every total and ceiling compare reads it as the credit it is.
- **A negative known customer price is not**: the money rails cannot carry it, so it is `unknown`
  with `negative_price_unsupported` (§4). A margin over a negative known cost is the same.
- **Zero is a known zero** (ruling 9). The unowned "amount at or below zero moves no money" guard on
  the billing and referral rails is retired. A known zero is a real price that moves nothing because
  it is nothing; a negative known price that somehow reached a rail is refused by name
  (`core.exceptions.NegativeKnownPriceRefused`, beside `MisalignedAmount`) and moves nothing, rather than being read as zero. The
  referral rail's compare on a value that is `None` for every unpriced posting goes with it.
- **No negative money moves in v1.** Carrying one — a credit on the rails, a negative wallet debit,
  a negative referral reward — is a later capability, and the reason exists so that capability can
  find what it must settle.

### 6. The total is the sum of what resolved; the lower-bound promise is retired

Every aggregate over amounts some of which are unresolved — the Task read, the cost and price
totals, the customer spend pool's known period charges, recovery's counts, the published
descriptions, the console and the spend-control vocabulary — makes one promise and no other:

> The total is the sum of economically resolved amounts. The existing omitted/unresolved count tells
> how many amounts are not included. When that count is zero, the total is complete.

"At least", "minimum", "floor", "lower bound" and every equivalent directional promise are removed
wherever they described such an aggregate: an omitted amount may now be negative, so a resolved
subtotal bounds the eventual total in neither direction. The existing counts stay as they were — no
count is multiplied, and none is added for negative amounts left out. The console marks a figure with
something left out as incomplete and says how many amounts it does not include.

### 7. The ceiling ASSESSMENT is `indeterminate` while anything is unresolved; ENFORCEMENT is unchanged

Two questions are kept apart on purpose (`core/crossing.py`):

- **The assessment** — `ceiling_status`, its used percentage and its remaining — is what a reader is
  told about where a unit stands. Whenever the unit carries an unresolved cost amount it is
  `indeterminate`, whatever the resolved subtotal, and its two figures are null; `within_ceiling`
  and `ceiling_reached` are only ever derived when everything has resolved. An unresolved cost is
  now asked before the line, and that order is the amendment.
- **The enforcement trigger** is the stop. It is a one-way safety action on RESOLVED observed COGS:
  the recording lane and the patrol still stop a unit when its resolved COGS total reaches the pinned
  Task ceiling, even while the complete assessment is `indeterminate`, and the stop is terminal. It is
  described everywhere — code, spec, ADR, glossary — as an enforcement trigger, never as proof that the
  eventual resolved COGS is above the ceiling. The acknowledgement's `stop_measured_micros` is the
  resolved COGS observed at that crossing (ADR-0019 §2).
- A later resolution, a negative COGS adjustment included, may move the derived assessment — even
  below the ceiling, so a stopped unit's assessment may fall back from `ceiling_reached` — and never
  reverses the stop. A negative known COGS lowers the total racing a ceiling, so the stop fires
  later, which is right for a real credit. There is no new status and no new reason for "stopped
  while indeterminate".
- **A late resolution reaches the unit.** Until #603 a unit's totals were written once, when a report
  was recorded, and nothing told the unit when an amount it counted as unresolved later resolved — so
  under this section's assessment a unit that ever carried one would read `indeterminate` for ever.
  The two settlement doors (`cost_settlement`, `price_resolution`) now call
  `TaskService.take_up_a_late_resolution`, which adds the resolved amount (a negative one included)
  to the unit's total and its parent's and stops counting it. It fires nothing itself. Its one
  consequence for enforcement is the existing rule applied to a figure that used to be stale: if a
  resolution takes an ACTIVE unit's resolved COGS to its ceiling, the patrol's sweep — the same
  `ceiling_reached` compare over the same columns — stops it on its next pass. A stopped unit stays
  stopped whatever a resolution does.
- **The completion and the unit's adjustment are one fact** (the owner's review of #614). Each
  door runs its conditional update and the call into the unit inside ONE transaction of its own — a
  savepoint under a caller's, the transaction itself in autocommit — so the two can never become
  separately durable. A replay finds no completion and adds nothing; an exception after the update,
  in the middle of the subtask → parent roll-up included, takes the completion back with it; and of
  two concurrent completions the conditional update admits one. The unit rows are read and written
  under their locks (parent before child), so a resolution racing a recording on the same unit loses
  neither amount. A resolution takes the posting before its unit — the reverse of
  `core/locking.py`'s order — and meets no cycle: the kernel cannot import a posting, and the
  recording path holds a unit while writing only the posting it is creating, which no resolution
  can hold.

### 8. The generated code: renderer contract 3, and a declared constant rendered (#584)

What a renderer is promised about a quantity changed, so `RENDERER_CONTRACT_VERSION` moved **2 → 3**
and every Blueprint fingerprint moved once, in the commit that moved it (ADR-0015 §3 records the
move). A renderer sends a quantity as text and never as a JSON number, refuses a float and a flag
rather than read one, and assumes no digit bound.

- **Python** (ADR-0016) passes an `int`, a `Decimal` or a `str`; the SDK sends its canonical text and
  refuses a float or a bool before anything is sent. CPython refuses `str()` of an int longer than
  4,300 digits and will not compile such a literal, so the SDK formats an int through `Decimal`, and
  an integer constant that long is written `int(Decimal("…"))` — still an int, with no digit cap.
- **Shell** (ADR-0017) passes a quantity with `--arg` as text, checked by the file's own `_ubb_exact`
  against the grammar and, for an `integer` Measurement, for whole-ness. The shell target's
  fifteen-digit refusal was a property of the jq number the value went through, and it goes with it;
  no runnable file asks for `--argjson`.
- **A quantity read off a supplier's response** is read exactly — an integer, or a decimal written as
  a string — or refused in words saying what to send instead. Python receives the response already
  parsed, so a float there is refused rather than read through its shortest text; the shell target
  reads the value as the response wrote it (ADR-0017 §6) and refuses a fraction or an exponent
  written as a number. The limitation is plain and stated in the generated comments: a
  `provider_response` decimal is recordable exactly only from a supplier that writes it as text or as
  a whole number.
- **A `constant` Measurement resolves `platform_known` and configured**, carrying its declared value
  as canonical text with its provenance, and the stored snapshot keeps the value (same content, same
  fingerprint; a changed value, a new one). Each target writes it as a typed exact literal in the
  MODULE only, with a provenance comment: an `int` or a `Decimal("…")` in Python, the canonical text
  in shell. `constant_measurement_not_renderable` is removed from the registry and every generated
  surface in the same commit, with the machinery that kept it. Verify sends a constant as generated
  code does, asks no sample of one, and refuses a sample for one. The recorded quantity equals the
  declared value: Seam B and Seam C hold an integer and a decimal constant, a negative one, and one
  with more digits than a binary float holds.

## Departures from frozen decisions

Each is quoted as it stood on `main` at `86d978d4`.

1. **The money-model decision, §6.2 item 2** (`docs/plans/2026-07-30-money-model-decision.md`):
   *"**Quantities are non-negative integers** on both ingest lanes — `dict[str, int]` (`schemas.py:71`),
   inherited by the async lane via `IngestEventIn(RecordUsageRequest)` (`schemas.py:116`). No
   floating-point value enters money arithmetic at any point."* The second sentence stands and is
   strengthened (§1: no binary float anywhere on the path); the first is superseded — a quantity is
   exact signed-decimal text.
2. **The door's "Fix 1"** (`apps/metering/usage/tests/test_negative_quantity_rejection.py`, deleted):
   *"Fix 1: negative measurements values must be rejected. Pydantic schema validator on
   RecordUsageRequest — endpoint returns 422, unconditionally (any card shape, strict mode or not)."*
   Overruled by #603: a negative quantity is valid (§1). The module's other half — what the bag still
   accepts — moved, unchanged in meaning, to `api/v1/tests/test_a_recorded_quantity_is_exact_text.py`
   (`WhatTheBagStillAcceptsTest`).
3. **R1 and R4's "half-up" text** (the money-model decision §5.2, and `core/money.py`): *"**R1 — a
   computed price line rounds half-up to whole micros, at the moment it is computed.**"* and *"**R4 —
   a percentage that produces a *charge* rounds half-up; a percentage that produces a *ceiling* rounds
   down.**"*; and `round_charge`'s *"Half-up division — R1 and R4's charging direction. … Ties go up,
   which is unbiased against the tenant everywhere except an exact half."* Superseded for the tie
   direction (§2): nearest micro, an exact tie away from zero. R2, R3 and R4's ceiling direction stand.
4. **ADR-0014 §2** (its "at or above, everywhere" consequence): *"A known total at the ceiling is
   `ceiling_reached`, whatever remains unresolved, and no later resolution softens it (#150 §4, #158
   §12.3)."* Superseded for the assessment by §7; the line still stops, and the stop is still never
   softened. ADR-0014 carries the amendment in place.
5. **The amount-status pairs' floor** (`core/amount_status_pairs.py`): *"`unknown` is information UBB
   does not have, and it is the reason a total over this column is a floor."* and the published cost
   wording *"An event whose supplier cost is unresolved adds nothing and is counted in
   `unresolved_event_count` beside it, so the total is a floor."* Superseded by §4's wording of
   `unknown` and §6's promise. The same reading in the published spec — *"`known_period_charges_micros`
   is the resolved period charges and a LOWER BOUND wherever `unresolved_posting_count` is not zero"*,
   and *"under `indeterminate` the percentage is a floor and the headroom a ceiling"* — goes with it,
   as does ADR-0010's recovery reading, amended in place.

## Consequences

- **Breaking on the published contract, in the pre-live lane** (ADR-0007 §5): a quantity's JSON type
  changes from integer to string on the recording routes, Verify's record, the acknowledgement echo
  and the detail read; the Blueprint diagnostic loses `constant_measurement_not_renderable`. The
  suppression file records each edge and names this ADR: the outbox payload's new required key as an
  entry, and the quantity's type as a reviewed comment, because `measurements` arrived after the
  `api-v1-launch` baseline and the cumulative gate sees no break against the published contract.
- **Every caller that sent a quantity as a number must send text.** The SDK does it for its callers
  and refuses a float; generated code does it on both targets.
- **A fraction is now recordable and costable exactly**, as is a quantity past 2⁵³ — a count that a
  float would have changed.
- **A negative customer price is not settled in v1.** It is unknown with its reason, not retried, and
  counted among the amounts left out until a negative-money capability selects it.
- **A unit with anything unresolved reads `indeterminate`**, including one that has been stopped. A
  reader who took `ceiling_reached` to mean "stopped" must read the stop, which is reported on its own.
- **The receipt and engine versions moved once each**, and the renderer contract once; every
  fingerprint, fixture and snapshot that moved with them was re-taken from the platform.

## Proof

| Claim | Pinned by |
|---|---|
| §1 — exact text through both routes, canonicalised, a JSON number refused, the value type decides a fraction, negatives and zero recorded | `ubb-platform/api/v1/tests/test_a_recorded_quantity_is_exact_text.py` — `EveryValueCrossesByteForByteTest`, `AValueIsCanonicalisedBeforeAnythingHoldsItTest`, `WhatTheWireRefusesTest`, `TheDeclaredValueTypeDecidesAFractionTest`, `ANegativeQuantityAndZeroAreRecordedTest`, `WhatTheBagStillAcceptsTest` |
| §2 — exact arithmetic, the tie away from zero, the fixed component as declared, the bound refused by name and per batch item | `ubb-platform/apps/metering/pricing/tests/test_a_quantity_is_costed_exactly.py` — `ARuleCostsAQuantityExactlyTest`, `AMarginIsTakenWithTheSameRuleTest`, `AnAmountPastTheMoneyBoundIsRefusedByNameTest`, `ANegativeCostIsAKnownCostTest`; `ubb-platform/core/tests/test_money.py` |
| §3 — a writer emits schema 2, the engine version (**superseded in part by ADR-0026**: every reader read 0, 1 and 2 until the cutover, #190, deleted the older shapes' readers; every reader now reads schema 2 and refuses anything else) | `ubb-platform/apps/metering/pricing/tests/test_a_receipt_holds_a_quantity_as_exact_text.py` — `TestAWriterEmitsSchemaTwo`, `TestTheRecoveryReaderReadsTheOneShape` |
| §4 — the reason required and nullable on every publisher | `ubb-platform/api/v1/tests/test_the_price_status_reason_is_required_and_nullable.py` |
| §4 — the table holds the reason as it holds the status: never written, cleared or carried in place, and cleared by the one resolution | `ubb-platform/apps/metering/usage/tests/test_a_price_resolves_once.py` — `TheStatusReasonMovesOnlyWithTheResolutionTest` |
| §4, §5 — a negative price is unknown with its reason, decided on the posting's total, not retried, counted | `ubb-platform/api/v1/tests/test_a_negative_price_is_unknown_with_a_reason.py` — `ANegativePriceIsUnknownWithItsReasonTest`, `TheSignIsDecidedOnThePostingsTotalTest`, `AFixedComponentDecidesTheSignOnItsOwnTest`, `AMarginOverANegativeCostTest` |
| §5 — the rails refuse a negative known price by name and move nothing | `ubb-platform/apps/billing/tests/test_outbox_handlers.py` — `test_a_negative_known_price_is_refused_by_name_and_moves_nothing`; `ubb-platform/apps/referrals/tests/test_handlers.py`; `ubb-platform/api/v1/tests/test_the_charge_reaches_the_rails_as_one_marked_posting.py` — `test_the_rails_would_have_refused_it_anyway` |
| §6 — no published description promises a direction for a total | `ubb-platform/api/v1/tests/test_openapi_contract.py` — `NoTotalIsPublishedAsABoundTest` |
| §7 — the assessment `indeterminate` whatever the resolved total; the stop fires on the resolved total | `ubb-platform/core/tests/test_crossing.py` — `test_something_unresolved_is_indeterminate_whatever_the_resolved_total`, `test_everything_resolved_at_or_above_is_reached`; `ubb-platform/api/v1/tests/test_one_rule_pins.py` — `test_resolved_at_the_ceiling_is_stopped_while_the_assessment_is_indeterminate`, `test_a_later_negative_resolution_moves_the_assessment_and_the_kill_stands` (the late-resolution door) |
| §7 — a late resolution reaches its unit exactly once: no replay adds twice, no failure leaves the posting known and the unit stale (subtask → parent included, and in autocommit), and concurrent completions cannot both win | `ubb-platform/apps/metering/pricing/tests/test_a_late_resolution_reaches_its_unit_once.py` — `AReplayAddsNothingTest`, `AFailureLeavesNeitherWrittenTest`, `WithNoTransactionOfItsOwnTest`, `ConcurrentCompletionsTest` |
| §8 — renderer contract 3, a constant resolved configured with its value | `ubb-platform/api/v1/tests/test_the_integration_blueprint.py`; `ubb-platform/api/v1/tests/test_a_constant_measurement_declares_its_value.py`; `ubb-platform/api/v1/tests/test_verifying_a_blueprint.py` — `TestAConstantIsSentAsDeclared` |
| §8 — both targets send a quantity as exact text and write a constant as a typed literal (Seam B) | `apps/codegen/tests/` — the execution suites' "a quantity" cases on both targets, and `writes and sends an integer constant longer than CPython compiles as a literal`; `ubb-sdk/tests/test_a_quantity_is_sent_as_exact_text.py` — `test_an_int_past_cpythons_text_conversion_is_sent_whole` |
| §8 — generated files, unmodified, record a decimal, a count past a float, and constants of both types, one negative, exactly (Seam C) | `tests/code_builder_execution/_scenarios.py` — `DECIMAL_QUANTITY`, `CONSTANT_QUANTITIES` |
