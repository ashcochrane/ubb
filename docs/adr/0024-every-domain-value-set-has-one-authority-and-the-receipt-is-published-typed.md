# ADR-0024: Every domain value set UBB publishes has one authority, the Pricing Receipt is published typed and version 2 only, and a selling rule states its method

**Status:** accepted
**Date:** 2026-10-28
**Decision records:** #190 spec part 2 (W4) · the owner's rulings of 2026-10-27 on slice 8's window W4,
§0.3 points 1–8 and amendments §0.4 A–E · #190 comment `5831552855` §1 (`RateOut` hides a rule's
method) · #190 comment `6354381879` (no audit opening row) · #147 §2.1
(`docs/plans/2026-07-31-markup-and-price-precedence-decision.md`) — *"A pricing rule … declares exactly
one method"*
**Amends:** #148 §4.6 (`docs/plans/2026-07-31-pricing-versions-decision.md`) — *"receipts created
under schema v1 → remain v1 → parsed with the v1 reader"*. Nothing is rewritten, so the section's rule
— *"A migration rewrites historical receipts only where there is a specific, audited correction
requirement"* — stands. What changes is the PUBLIC read: the three responses that publish the record
type it as version 2 only, so a v0 or v1 record no longer validates there. The evidence is ruling 3:
UBB was never deployed, a receipt older than 2 exists only on a development database, and such data
is not product history — W6 resets it at the cutover rather than the launch contract widening to
carry it. The internal readers of v0 and v1 stay until W6 removes them.
**Companion:** ADR-0006 §2 (one canonical public term per concept) · ADR-0007 §3–§4 (no provisional
public vocabulary; a reviewed break) · ADR-0008 §2–§4 (the registry's kinds; identity is the
registry's, expression the catalogue's) · ADR-0020 §3 (the receipt's versions and its open `detail`)

## Context

ADR-0008 made the registry the authority for what a value is called and the label catalogue the
authority for how it is worded, and installed G2, G4 and G6 to hold consumers to it. At the end of
slice 7 the migration ledger still owed twenty-five entries against those gates: the audit
catalogue, which the registry declared and the backend restated inline, and twenty console sites
that worded a value by hand or by title-casing its token. Four published shapes still hid fixed
values from the gates — the Pricing Receipt, published as an untyped object on three responses; the
grouped-value status, a bare list of strings; the grouping-field schema names, under a retired word;
and a pricing rule's method, which `RateOut` did not publish at all, so a margin rule (stored with
zero terms) read as a price of zero. And storage hid meaning in two places: a null method on a
selling rule that the resolver read as `direct_event_price`, and wallet transaction types spelled
outside the registry's token rule.

The owner's §0.4 A set the scope: every canonical DOMAIN concept and domain value set UBB publishes
has one declared vocabulary authority; API routes and fields keep OpenAPI's, and error identifiers
keep `openapi/error-codes.json`'s. The registry is not a register of every public symbol.

## Decision

### 1. Twenty-one value sets are declared, each with its kind, and each consumer holds it by reference

`audit_resource_type`, `actor_kind` (open — ADR-004 §4 made it so), `role`, `member_status`,
`invitation_status`, `enforcement_mode`, `stop_scope`, `wallet_transaction_type`, `grant_kind`,
`grant_status`, `grant_source`, `usage_invoice_status`, `skip_reason`, `tenant_invoice_status`,
`billing_period_status`, `reward_type`, `referral_program_status`, `referral_status`,
`calculation_method`, `grouping_field_value_status` and — from the owner's review of #620 — `markup_rung`,
the one value a Pricing Receipt's markup provenance names (`tenant_default`): a module constant
while the receipt was published untyped, a closed value set once #558 typed it, and a one-value set
is still a value set. The receipt's construction boundary refuses a rung outside it
(`receipts._validate_provenance`), as it refuses an undeclared subject type: a published enum marks
the contract and checks nothing. Each names its backend, contract and console
consumers; the backend builds its `choices=` or constants from the generated names, the contract
marks every field carrying one, and the console renders it through the concept's generated label
keys — an open one through `components/shared/open-set-value.tsx`. The ingest-rejection map was not
declared: its values are error codes, owned by the error catalogue (ruling 8).

### 2. A closed public concept advertises only values that can occur — `withheld_values`

A closed concept may declare `withheld_values`: values that stay declared while no producer may
write one and the contract does not advertise it. The compiler refuses a withheld value the concept
does not declare, and withholding every value. The generated Python constants bind
`<CONCEPT>_WITHHELD_VALUES`; the decision document advertises the declared set less the withheld one.
The exclusion lives in the registry because the Django-free contracts suite and the spec export must
learn it from the same place the backend does.

Withholding is a precise contract tool, and the owner's review of #620 fixed what it means, each
point held by `tests/contracts/test_end_state_vocabulary.py`: a withheld value is advertised on no
enum; no ordinary writer can emit it (production code names its generated constant only where a
consumer filters it out); a value with a current legal production writer must not be withheld, so the
first writer un-withholds it in the same commit; it is never a compatibility alias; and it is never a
parking place for a planned value — the exact set is pinned, each with its reachability proof.

There are four, decided by the reachability rule (a legal production path: a public route, an
external synchronisation, an admin or domain operation, an intentional writer — never model choices
or raw SQL):

- `audit_action`'s `system.preproduction_model_cutover`: no opening row is ever written (#190
  `6354381879`); the registration stays until W6 retires it, and until then `record()` refuses it by
  name. The one temporary, W6-owned case: W6 deletes the value and the exclusion together.
- `tenant_invoice_status`'s `void` and `uncollectible`: legitimate states of a platform-fee invoice
  that nothing creates today. The status's only writers are the platform-fee task (`finalized`) and
  the `invoice.paid` webhook (`paid`); Stripe's `invoice.voided` and `invoice.marked_uncollectible`
  reach a reconciler that returns for an event with no connected account, and a platform-fee invoice
  lives on UBB's own Stripe account.
- `referral_program_status`'s `paused`: a legitimate state the backend already reads as live beside
  `active`, which no route creates — create takes `active`, DELETE writes `deactivated`, reactivate
  writes `active`, and the update body carries no status.

The three are filtered out of their models' `choices=` (`tenant_billing/0016`, `referrals/0009`) as
well as out of the contract.

### 3. The audit catalogue is the registry's

The eight registrations nothing ever wrote are deleted, and none becomes a retired alias, because
none has a same-concept successor. None of the sixty-nine written actions spells a retired alias, so
no rename was owed. `apps/platform/audit/actions.py` derives the recordable set from the registry,
`record()` refuses an undeclared resource type, and every production writer names an action and a
resource type by reference.

### 4. The Pricing Receipt is a typed schema, version 2 only

`PricingReceipt` is published on the acknowledgement (required, never null — every recording writes
one), on the batch item (null only on a rejected item) and on the event detail (required — the
recording path and the Charge projection both write one, so every posting has a receipt). Every
level is closed except `detail` and `provenance`, which ADR-0020 §3's additive rule keeps open: each
types the keys UBB writes and admits another, and each publishes exactly what was stored — a typed
key the record does not hold stays absent rather than arriving as null. The twelve closed concepts
inside carry their markers — the twelfth, `markup_rung`, added by the owner's review of #620. There is no legacy branch, and the version is held in the type itself
(`receipt_schema_version` is the constant 2), so a record declaring an older version is refused even
where nothing else in it differs. A component's per-key quantity is published
under the key it is stored under — the rate-arithmetic sense `measurement_key.retired_senses` keeps
alive and #366 ruled stays, not the inline total #272 retired — and the gate that proves that total
gone admits exactly that one schema and pointer. Each total carries its own description: present
exactly when its section's status is `known`.

### 5. A selling rule states its method; nothing else states one

`ck_rate_a_selling_rule_states_its_method`: a rule carries `pricing_method` if and only if it sits in
a Pricing Book. A cost book's rate, and a rule in no book (which no production path writes), carry
null. `pricing/0034` stated `direct_event_price` on every selling rule that held null — what
resolution already read it as, so no price moved. A publish writes the method where a body is
silent, a cost book's change naming one is refused by name, and the resolver refuses a rule with none
rather than defaulting. This is #147 §2.1's rule held in storage rather than a departure from it.

The outputs say exactly what storage proves (the owner's review of #620), by what each row CAN be:
`RateOut.pricing_method` and `RuleTermsOut.pricing_method` (a publish diff's before and after, for
either kind of book) are required and nullable, null exactly on a cost book's rate;
`InheritedPricingRule.pricing_method` — always a selling rule, the one a customer is priced from — is
required and never null. The request bodies (`BookRateChangeIn`, `CustomerOverrideIn`) keep their
optional method, because their write contract means "the server states `direct_event_price`".

### 6. The wallet's vocabulary is lowercase and spelled once

`wallets/0014` moves every stored transaction type to the registry's lowercase token and the grant
source's run-together spelling to `auto_top_up` (ADR-0006 §2); two `CHECK`s admit only the registry's sets. No
form other than the registry's is accepted afterwards. The run-together spelling is a retired alias of
`grant_source`, so the sweep refuses it on every living surface, and every other spelling of the same
concept moved with it (the owner's review of #620): a top-up attempt's `trigger` (`topups/` migration),
the SDK's `configure_auto_top_up`, the `usage.recorded` payload's `auto_top_up_attempt_id`, the
automatic credit's idempotency prefix and the connector's handler. No public input accepts a grant's
source. The same rule holds a usage invoice's skip reason
(`invoicing/0011`): an invoice that was not skipped held `""` and the read translated it to null; it
stores null now, and `ck_usage_invoice_skip_reason_known` admits null or the registry's six.

### 7. One name per counted concept, and the shared count name is retired

The eight public fields that shared one count name take the name of what each counts:
`recorded_events` on a unit of work (and the billing period's column), `count` on an economic
measure's figure slot, `posting_count` on the four posting-count reads and the cost accumulator,
`rewarded_posting_count` on the referral reward accumulator. The shared name is a retired alias
of `analytics_measure`, so the sweep refuses it on every living surface — and the console words a
posting count as postings (the business rollup, a stop episode's itemised set), never as events, the
recorded-events measure's word. `EconomicMeasureOut.count` is required and nullable (the owner's
review of #620): present on every measure, the count measure's figure, and null on a money measure —
"missing" and "does not apply" never read the same, and no zero stands in.

### 8. The grouping field's names carry no retired word (#541)

`GroupingFieldIn`, `GroupingFieldOut`, `GroupingFieldRegistryIn`, `GroupingFieldRegistryOut`, the
internal `GroupingFieldService` / `GroupingFieldError` family, and the audit resource type
`grouping_field_registry`. A case-insensitive contract gate holds component names, generated SDK
models and audit resource types; it is not a ban on the English word. The database constraint names
`uq_dimension_*` and the column `TaskType.required_dimensions` are W6's, where the squash names them.

## What proves it

| Rule | Test |
|---|---|
| §2 — the compiler's rule | `tests/contracts/test_vocabulary_registry.py` — `test_a_withheld_value_the_concept_does_not_declare_is_rejected`, `test_withholding_every_value_is_rejected`, `test_an_open_concept_cannot_withhold_a_value`, `test_a_withheld_value_stays_declared_and_leaves_the_occurring_set` |
| §2 — the generated exclusion | `tests/contracts/test_generated_vocabulary.py` — `test_a_withheld_value_is_bound_in_its_own_set_and_kept_in_the_whole` |
| §2, §3 — the ledger refuses the withheld action and an undeclared resource type; writers by reference | `ubb-platform/api/v1/tests/test_the_audit_catalogue_is_the_registrys.py` — `TheLedgerRecordsOnlyWhatTheRegistryDeclaresTest`, `EveryWriterNamesTheCatalogueByReferenceTest`, `TheFeedPublishesTheCatalogueTest` |
| §4 — the typed receipt, published as stored, null only when rejected, v2 only | `ubb-platform/api/v1/tests/test_the_pricing_receipt_is_typed.py` — `EveryRouteCarryingTheRecordPublishesItTypedTest`, `TheTypeIsVersionTwoAndOpenOnlyWhereTheRuleSaysTest` |
| §4 — the whole stored record, served unchanged by the typed serializer | `ubb-platform/api/v1/tests/test_metering_endpoints.py` — `test_a_receipt_is_served_whole_and_not_rewritten` |
| §4 — the component's stored quantity is the one admission the inline-total gate makes | `tests/contracts/test_the_inline_unit_total_is_gone.py` — `test_the_admission_is_used_exactly_where_it_says` |
| §4 — every closed concept inside is marked | `tests/contracts/test_openapi_known_values.py` — `test_the_pricing_receipt_marks_every_closed_concept_inside_it`, `test_negative_control_an_unmarked_closed_value_in_the_receipt_is_found` |
| §5 | `ubb-platform/api/v1/tests/test_a_selling_rule_states_its_method.py` — `TheRatesRouteSaysEachRulesMethodTest`, `APublishStatesTheMethodTest`, `TheTableHoldsTheRuleTest`, `TheResolverRefusesARuleWithNoMethodTest`, `TheBackfillStatesTheMethodTest` |
| §6 | `ubb-platform/api/v1/tests/test_the_wallets_vocabulary_is_the_registrys.py` — `TheLedgerSpeaksLowercaseTest`, `TheTableRefusesAnotherSpellingTest`, `TheMigrationMovesEveryStoredRowTest` |
| §1 — a skip reason and a reward type at their doors | `ubb-platform/api/v1/tests/test_the_billing_and_referral_vocabulary_is_the_registrys.py` — `AUsageInvoiceSaysWhyItWasSkippedTest`, `AProgrammesRewardTypeIsTheRegistrysTest` |
| §6 — a skip reason stored as null, and `invoicing/0011` run for real | `ubb-platform/api/v1/tests/test_the_billing_and_referral_vocabulary_is_the_registrys.py` — `TheSkipReasonMigrationStoresNoReasonAsNullTest` |
| §1 — the role's rank is the registry's order | `tests/contracts/test_end_state_vocabulary.py` — `test_the_role_rank_is_the_registrys_order` |
| §2 — what withholding means, and the four withheld | `tests/contracts/test_end_state_vocabulary.py` — `test_the_withheld_values_are_exactly_these_and_each_says_why`, `test_a_withheld_value_is_advertised_nowhere`, `test_no_production_writer_names_a_withheld_value`, `test_withholding_is_never_a_compatibility_alias` |
| §1 — a markup's rung is the registry's, refused at the boundary otherwise | `ubb-platform/apps/metering/pricing/tests/test_a_markup_charge_can_be_explained.py` — `test_a_rung_outside_the_registrys_set_is_refused_at_the_boundary` |
| §5 — each rule output states what storage proves | `ubb-platform/api/v1/tests/test_a_selling_rule_states_its_method.py` — `TheContractStatesTheMethodWhereItAlwaysExistsTest`, `test_a_diff_states_a_selling_rules_method_and_a_cost_rates_null` |
| §7 — a measure's count is present or null | `ubb-platform/api/v1/tests/test_the_one_economic_query.py` — `test_every_measure_states_its_count_and_none_invents_a_zero` |
| §8 | `tests/contracts/test_no_published_name_spells_the_retired_grouping_word.py` — `test_no_component_name_spells_the_retired_grouping_word`, `test_no_generated_sdk_model_spells_the_retired_grouping_word`, `test_no_audit_resource_type_spells_the_retired_grouping_word` |

## Consequences

- **The contract breaks deliberately, in the pre-live lane** (ADR-0007 §5). Twenty concepts reach it
  as enums; the receipt changes from an open object to a typed one; a skip reason that was `""` is
  null; four webhook fields become required; eight fields and four components are renamed. A break on
  a surface present at `api-v1-launch` is a generated entry in the suppression file; one on a later
  surface is a reviewed comment.
- **An old development database must be reset**, not accommodated: a v0/v1 receipt fails the public
  type, and W6 removes the internal readers at the clean cutover (§0.4 D).
- **Economically neutral** (§0.4 E). No amount, posting selection or report arithmetic moved;
  `PRICING_ENGINE_VERSION` stays 3.0.0.
- **A later closed concept that must stay declared without occurring** takes `withheld_values`, never
  a hand-written exclusion in one consumer.
