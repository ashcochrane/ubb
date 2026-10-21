# ADR-0021: An agreed price is a second kind of Pricing Book line, the regime decides why an event has no price, and a kind sold whole is ready by the prices a tenant published

**Status:** accepted
**Date:** 2026-10-21
**Decision records:** #553 — the final specification (comment `6069879273`, 2026-10-08) and the
owner's rulings it settles (A6, the product gate; A9, the totals; C1 and C2, the pricing result) ·
#586 — the owner's readiness ruling of 2026-10-20 on #553 (`6279555404`) and its clarification the
same day (`6279967254`)
**Companion:** ADR-0013 is the Charge this prices, and its §5 tie-break is superseded by §5 here;
ADR-0012 is the frozen pricing mode a start reads; ADR-0009 is the publish act a price now travels
in; ADR-0020 §7 is the one-transaction rule §3 applies; ADR-0015 §3 is the renderer contract that
does not move (§6); ADR-0018 §8 is amended by §6; ADR-0007 §5 is the pre-live lane every break
below travels in

## Context

A tenant could declare a kind of work sold at one agreed price (ADR-0012) and could not say what the
price was. The Pricing Book held measured-quantity rates and nothing else; the publish act accepted
only those; no route read an agreed price; the line's table had no writer at all. So every start of a
fixed-price kind was refused for a tenant that bills through UBB, and a tenant that does not got no
revenue figure for the work its margin reporting exists for.

Three earlier decisions made the gap worse than a missing route. Whether UBB could know a price at
all turned on whether the tenant collected payment through UBB: Pricing Books were behind the billing
product. A metering-only tenant's fixed-price postings said why they had no price by naming the
tenant's billing mode (`tenant_not_billing`) rather than the regime that applied. And the Charge a
delivered unit of work produces reached the rails as one posting but never the unit of work's own
totals, so a run's billed total left out the one figure it was sold for.

The Code Builder (#586) is the first consumer that has to ask "is this kind priced?" of a whole
tenant rather than of one start, and the owner's ruling of 2026-10-20 settled what that question is
allowed to read.

## Decision

### 1. A book change names its line: the contract's first discriminated request body

A change in the Pricing Book publish act is a discriminated union on a required field, **`line`**:
`rate` (the body that existed, unchanged apart from the field) or `agreed_price` (`kind` —
`add` | `reprice` | `retire`; `task_type`; `agreed_price_micros`, absent on a retirement). The diff a
draft answers is the same union. Each variant's `line` is a one-value literal, and the export writes
the union as `oneOf` with a `discriminator` mapping and no `enum` on the field.

**The rule, for every later body like it:** a request body that can carry more than one kind of
thing is a union discriminated by a REQUIRED field named for what it carries, and each variant
requires its own fields. A body with no discriminator is refused by name, and so is one naming a
line nobody defined; nothing is inferred from which fields happen to be present. The rate variant's
schema is `BookRateChangeIn`, and `BookChangeIn` names the union — the name a consumer already held
now names what a change is.

The first commit of #553 proved the union through all three consumers before any route used it: the
spec export, the console's typed client and the SDK generator (which ignores the mapping and
dispatches on each variant's literal). The break is a deliberate pre-live one (ADR-0007 §5). The
Pricing Book routes arrived after `api-v1-launch`, so the cumulative gate does not report it, and
it is recorded as a reviewed COMMENT in `openapi/oasdiff-err-ignore.txt` naming this ADR — an entry
there would be inert, and the gate fails an inert entry.

A change that OPENS a line — an add, a reprice — is refused for a kind of work nobody declared, one
retired, or one declared only as contained work. A retirement opens nothing, so a line whose kind was
retired since can still be closed.

### 2. The provenance split: an agreed-price line carries the rate side's history

An agreed-price line (`TaskPrice`) carries what a rate carries: the book version that opened it and
the one that closed it, and a `lineage_id` a reprice hands to its successor. `valid_from` is frozen
and `valid_to` is set once, by a database trigger (`trg_task_price_declared_transitions`) as for
rates. The money column is `agreed_price_micros`, the public name; there is no currency (USD micros,
no FX). A zero is a price; a negative is refused.

The publish record lists **`opened_agreed_price_ids`** and **`closed_agreed_price_ids`** beside
`opened_rule_ids` and `closed_rule_ids`, which keep naming rates only: an agreed price is not a rule,
and "rule" is not widened to hold it. The publish act is the only writer of a line. A book's agreed
prices are read through `GET /api/v1/metering/pricing/books/{book_id}/agreed-prices` (open lines by
default, every version with `include_history`, the line in force at `as_of`), the rates read's
sibling, and the planner's diary boundary reads both kinds of line.

A start still pins three things — the amount, the line, the book's version at resolution — and the
Charge carries the line and the version.

### 3. The totals rule: the Charge is in what its unit of work billed (A9)

A Charge's projection adds its posting's amount to the top-level Task's **billed** total, and to
nothing else: never `total_provider_cost_micros`, never `event_count`, never the unpriced count. The
close response carries it when that close created the Charge.

The posting and the total are ONE FACT, by ADR-0020 §7's standard: the projection writes the posting
and takes the amount into the Task (`TaskService.take_up_a_charge`) inside one transaction of its
own, nested in the close's. A replayed close adds nothing, a failure after the posting is written
leaves neither, and two racing closes add once.

### 4. The metering-floor gate: collection mode does not decide whether UBB may know a price (A6)

Pricing Books take the cost book's metering floor everywhere — create, list, read, withdraw, the
publish act, the lines reads and a customer's overrides. **Billing/collection mode does not decide
whether UBB may know the agreed customer price**, and the Pricing Book gate's docstring says so.
Plans stay behind the billing product, because their fee axes are subscriptions and Stripe; the
billing outbox handlers stay behind it too, so a metering-only tenant's priced postings and Charges
move no wallet and no fee.

### 5. The regime decides the reason (C2)

A fixed-price unit of work's event postings are `not_applicable` with the reason
**`fixed_task_pricing` for every tenant**: the pricing regime that applied decides the reason, and
the tenant's billing mode is not encoded again in a pricing result. `tenant_not_billing` lost its
only producer, so it was removed in the same change — its registry value, the posting's check
member, every generated follower and every reader that branched on it. The pricing engine's version
does not move: the reason is not an amount.

**A one-time, pre-live exception to resolve-once.** Every existing posting holding the old value was
a metering-only tenant's fixed-price event posting, whose truthful reason is `fixed_task_pricing`, so
the owner ruled the rewrite. The posting's price trigger refuses any change to the reason, from a
migration too. Migration `usage/0047` lifts exactly that trigger
(`trg_posting_price_transitions`) for exactly one UPDATE, inside the migration's one transaction,
and enables it again in the same transaction; the trigger's function is not touched. A test pins
that afterwards the trigger is enabled and still refuses a reason rewrite through every door. UBB is
not deployed (ADR-0007 §5), and this exception is spent: a later change of the same kind earns its
own decision.

A sealed Pricing Receipt is not rewritten. One that holds the historical value still reads — the
receipt is served as a record the reader does not check against the live registry — and nothing new
produces it.

### 6. A kind sold whole is ready by the prices the tenant PUBLISHED (#586)

**A Blueprint is customer-independent.** For a kind of work sold at one agreed price, readiness reads
the tenant's published pricing configuration and nothing else: the default Pricing Book, the book of
every live Plan, and every customer's own book — every book some start could price from
(`pricing_service.the_books_a_start_can_price_from`, over the kernel read
`plans.queries.pricing_books_of_live_plans`). It never selects or inspects a runtime customer,
never depends on how many customers there are or which Plan any of them is on, and never picks the
customer whose price would make it look complete. An archived Plan's book counts for nothing, because
no start reaches it.

- **Blocked** only where the tenant bills through UBB and no such book holds an agreed price in force
  for the kind now: every start would then be refused. Diagnostic `agreed_price_missing`.
- **Never blocked** for a tenant that meters without billing: nothing refuses its start.
- **Advised, symmetrically, whenever the DEFAULT book holds none** — even where a Plan's or a
  customer's own does: `default_agreed_price_missing_refused_at_start` where the tenant bills
  (customers without their own or a Plan price will be refused at start) and
  `default_agreed_price_missing_no_revenue_figure` where it does not (they will have no
  authoritative revenue figure). Two members rather than one because what follows differs by posture
  and a diagnostic carries no prose: a renderer, never told the posture, words each from its code.
- "Complete" means the file is fully generatable and a runtime pricing path exists. It does not
  promise every customer's start is admitted.

All three are reported over a new configuration object kind, **`agreed_price`**, keyed by the kind of
work, with the field `agreed_price_micros`. None offers a request: an agreed price is declared on a
Pricing Book's editor, which the console links to, and the publish that declares one names a book by
its row id, which a diagnostic never carries.

**The snapshot keeps the outcome and the default book's price, and nothing customer- or
Plan-specific.** For a kind sold whole — and only then, so no other snapshot's bytes moved — the
snapshot's configuration holds `has_any_effective_runtime_agreed_price` and the default book's price
with where it came from (the book's key, the version that opened the line, `valid_from` and
`valid_to`). No customer id, no Plan id, no customer count and no other book's amount. So repricing
one customer's deal or a Plan's price moves no fingerprint while the outcome is unchanged; adding the
first price anywhere or retiring the last does; and repricing the default book does. No call's token
carries the price, so no generated file holds one.

**Verify materialises the default book's price and picks no other.** The run publishes the kept
price into its own default book through the act and is charged it on delivery. Where only a Plan's
or a customer's own book holds one, the run's customer — on no Plan, with no deal — is refused at its
start where the tenant bills, and Verify answers that real refusal; the advisory said so first.

The renderer contract stays 3 (ADR-0015 §3): nothing a renderer is handed means anything new. The
renderer catalogue moves 8 → 9 for the three remediation entries.

### 7. What this supersedes

Named and quoted, with the 2026-10-08 rulings as the evidence:

- **The Stage A design decision 10**, *"cost→metering, price→billing"* — superseded by §4. A price
  is something UBB may know whatever the tenant collects through it.
- **#141 §4.2's citation of that gate** — superseded by §4 with it.
- **#418's tie-break, *"posture wins"*** (the charging-modes decision: *"`not_applicable` carries a
  reason from a closed list, and posture wins when both apply"*) — superseded by §5. ADR-0013 §5,
  which carried it, is marked superseded in part.
- **ADR-0018 §8's agreed-price clause** (*"until the snapshot carries it, such a run is refused at
  its start and says so"*) — amended by §6.

## Consequences

- A tenant declares, reprices and retires an agreed price in the same act, diff and record as its
  rates, and reads it back typed, whichever product it holds.
- A run's billed total is what it was sold for; its supplier cost and its event count are what the
  work cost and did.
- A metering-only tenant's fixed-price postings point at the Charge that holds their revenue.
- A Blueprint for a kind sold whole is the same Blueprint whoever the tenant's customers are, says
  when nobody can be priced, and says when only some can.
- The contract has its first discriminated body and the rule the next one follows.

## Proof

| Rule | Held by |
|---|---|
| §1 the union, through all three consumers | `ubb-platform/api/v1/tests/test_a_book_change_names_its_line.py`; `ubb-sdk/tests/test_a_book_change_names_its_line.py`; the console's `features/pricing/api/book-lines.test.ts` |
| §1–§2 the act's plan, refusals, provenance and record | `ubb-platform/api/v1/tests/test_an_agreed_price_is_declared_through_the_publish_act.py` |
| §2 the window held by the database | `ubb-platform/apps/metering/pricing/tests/test_an_agreed_price_window_is_held_by_the_database.py` |
| §2 the read | `ubb-platform/api/v1/tests/test_a_books_agreed_prices_are_read.py` |
| §3 the totals, one fact with the posting | `ubb-platform/api/v1/tests/test_a_charge_reaches_its_units_billed_total_once.py`; end to end for both postures: `test_an_agreed_price_is_charged_end_to_end.py` |
| §4 the gate | `ubb-platform/api/v1/tests/test_book_api.py` — the `metering_only_can_*` cases and `test_plans_stay_behind_the_billing_product` |
| §5 the reason, and the one-time rewrite | `ubb-platform/apps/metering/pricing/tests/test_why_a_price_does_not_apply.py`; `ubb-platform/apps/metering/usage/tests/test_the_regime_decides_why_a_price_does_not_apply.py` |
| §6 readiness, the snapshot, the fingerprint and Verify | `ubb-platform/api/v1/tests/test_the_blueprint_resolves_an_agreed_price.py`; the census in `test_the_integration_blueprint.py`; the committed fixtures `fixed-price`, `fixed-price-unpriced`, `fixed-price-priced` and their Verify answer (`test_the_renderers_fixtures_are_what_the_platform_answers.py`) |
| §6 run unmodified on every target | Seam C scenario 11, `tests/code_builder_execution/_scenarios.py` (`FIXED_PRICE`) |
