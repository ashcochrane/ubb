# ADR-0023: UBB v1 is US dollars only — refused at its own doors, quarantined from Stripe, read from the record on the way out, and never converted

**Status:** accepted
**Date:** 2026-10-27
**Decision records:** #145 §7.1 (`docs/plans/2026-07-30-measurement-vocabulary-decision.md`) — *"v1 is
USD-only. Every amount participating in supplier costing, customer charging, wallets, refunds,
invoicing and margin reporting is USD, enforced at both boundaries … Non-USD monetary input is
rejected, never converted"* · #555's ruling (comment `5785420835`) and its eighth drift site
(`5795340535`) · the owner's rulings of 2026-10-26 on slice 8's window W3 (#190): ruling 4
(`currency_locked` retires) and amendment A (a refusal at UBB's own doors is not the quarantine of an
external source fact)
**Amends:** #142 §2.2 (`docs/plans/2026-07-30-money-model-decision.md`) — *"`Tenant.default_currency`
stops defaulting to `usd` and becomes **unset** until chosen"*, with a typed `currency_not_set`
refusal on every money write until it is. Under USD-only there is one admissible value, so there is
nothing to choose and the database default names it. The rest of §2.2 stands, and is built here:
*"`_currency_locked_reason` and its five conditions are deleted."*
**Companion:** ADR-0002 (a `CHECK` holds an invariant no business situation can make false — which
this one is, unlike a spend floor) · ADR-0006 §1 (`_micros` means millionths of a currency unit) ·
ADR-0007 §2 (a model-level guard is a courtesy; the database is the rule) and §4 (an accepted break
is generated, never hand-written)

## Context

#145 §7.1 ratified USD-only on 2026-07-30 and nothing has amended it. It was never written as an
ADR and never backed by a test, so it lived only in a dated document that `CLAUDE.md` calls frozen
history. Later tickets stopped seeing it, and #555's reconciliation (`5785181115`) found the code had
drifted past it at eight sites:

1. the tenant door admitted eighteen currencies, and two tests required non-USD success;
2. no `CHECK` held any currency column;
3. the outbound Stripe calls stated `usd` themselves instead of reading the record (#565);
4. the currency lock missed postings;
5. the foreign-currency quarantine #142 §4 decided was never built (#564);
6. the Cost Book's default key promised a default per currency;
7. supplied revenue checked a currency against the eighteen;
8. a reported cost's pinned currency did the same.

The eighteen come from `core.money`'s minor-unit table, which gives each currency's minor unit.
Nobody ever proposed it as the set of currencies UBB admits. A table built to keep
twenty literals honest had become the policy by being the only list in sight.

## Decision

### 1. The rule

> UBB v1 economic/configuration admission is USD-only. Explicit non-USD money/configuration supplied
> through UBB's own economic doors is refused. A foreign-currency fact received from an external
> integration is preserved as a source fact and quarantined before it can enter USD economics. It is
> never converted, relabelled or counted as USD.

There is no FX anywhere in UBB, so no conversion would be correct. Currency stays a stored column on
every record that carries money: a fact about money names its currency (#145 §7.2).

### 2. One policy, beside the representation table — never in place of it

`core.currency_policy` is the one place admission is asked:
- `admit_currency` returns the stored spelling of US dollars or raises `UnsupportedCurrency`;
- `is_admitted` is the same question, asked without raising;
- `usd_only_check` builds the database's half of the rule for one column.

`core.money` keeps every currency it knows. That table is **representation**: it lets UBB read a source
fact in euros honestly, and lets a generated integration convert a supplier's amount from its own
minor unit without mis-scaling it (§6). Shrinking it to US dollars would confuse what UBB can represent with what it
admits. Admitting a second currency is a decision about FX, never an edit to that table.

### 3. UBB's own doors refuse, all with the one code

Every door below asks the policy and answers `unsupported_currency` (422), the error catalogue's
existing code. Nothing is recorded or written.

| Door | What it refuses |
|---|---|
| `PATCH /api/v1/tenant/config` | `default_currency` other than US dollars |
| `POST /api/v1/metering/usage` and `/usage/batch` (and the Code Builder's verification, which records through the same function) | an event's `currency` — whole-request on the single route, per item on the batch, where `unsupported_currency` joins `ingest_rejections` |
| `POST /api/v1/metering/pricing/cost-books` | a Cost Book's `currency` |
| a reported cost's declaration | a pinned `currency` (blank stays legal: a path into the supplier's response names it instead) |
| `POST /api/v1/customers/{id}/supplied-revenue` | the stated figure's `currency` |

`usd` is admitted in any case and surrounding space, and is stored as `usd`.

### 4. The database holds every economic currency column

Each column UBB's economics admit carries a `CHECK` from `usd_only_check`:
- `ubb_tenant.default_currency` (`ck_tenant_default_currency_usd`) — the column #555's ruling named,
  because the admin form edits every column of a tenant;
- `ubb_wallet`, `ubb_credit_grant`, `ubb_rate`, `ubb_charge`, `ubb_cost_book`, `ubb_posting`,
  `ubb_tenant_supplied_revenue`, `ubb_customer_usage_invoice` (`ck_<table>_currency_usd`);
- `ubb_reported_cost_mapping` (`ck_reported_cost_currency_usd`), which admits the empty string beside
  US dollars.

`Tenant.clean()` asks the policy as well. So a `save()` from the admin form or a seed meets a named
validation error, and only a write that never calls `save()` meets the constraint.

**The Stripe mirror's two currency columns are spared, and declared so.**
`StripeSubscription.currency` and `SubscriptionInvoice.currency` record what Stripe sent. A `CHECK`
there would make the database refuse the very evidence the quarantine (§6) keeps. Each model names
its column in `SOURCE_CURRENCY_COLUMNS`, which is the `CHECK`'s only exemption.

**A database default of `usd` stays** (#555's ruling). The load-bearing rule is that *explicit*
non-USD input is refused, and no default can disguise an externally supplied amount, because an
external source fact never reaches an economic column (§6).

**Pre-cutover data is reconciled by refusing, not by rewriting.** Each migration that installs a
`CHECK` first runs `refuse_rows_outside_the_policy`. If any row holds another value it stops, names
the rows and changes nothing. A stored `'USD'` is refused the same way, because lower-casing it would
decide a row's meaning on a reader's behalf. Nothing is deployed, so on every real database the step
finds nothing.

### 5. The currency lock retires

With US dollars the only legal value, "money exists, so the currency may not change" has nothing to
guard. A tenant cannot leave US dollars by any path, including the admin form, because the `CHECK`
covers its column. So `_currency_locked_reason`, the `currency_locked` problem code, the SDK's
`CurrencyLockedError` and the console's lock message are deleted. A non-USD attempt answers
`unsupported_currency`, and re-sending `usd` is a 200. #142 §2.2 had already deleted the five-condition
probe on its own terms.

### 6. Representation is not admission: the generated integration converts honestly and UBB refuses

A reported cost may name its currency by a path into the supplier's response. The generated
integration then reads the code the supplier returned and converts the amount from **that currency's
own** minor unit. `event_types/reported_cost.pin_currency` is the executable definition of that step,
and the renderer's mirror of it reads the same eighteen-entry table, pinned equal to `core.money`'s.
Both are representation. Admission is not decided there. The code travels to UBB beside the amount,
and the recording routes refuse anything but US dollars (§3). A second copy of "USD only" in the
renderer would be a second policy in every tenant's repository.

### 7. A foreign-currency fact from Stripe is kept and quarantined (#564)

A connected account may hold a subscription, and issue its invoices, in a currency UBB never admitted.
UBB does not refuse what Stripe already did: refusing at the webhook would only make Stripe retry, and
dropping the row would make that revenue read as a confident zero (#141). So every mirror writer reads
Stripe through one module (`apps/subscriptions/stripe/items.py`), and each row keeps:
- `currency` — what Stripe named, in its canonical spelling, whatever it is;
- `source_amount_minor` / `source_amount_paid_minor` — Stripe's own integer, exactly as sent, in that
  currency's minor unit. It is never scaled by the tenant's minor unit, and it is never stored under
  `_micros` (ADR-0006 §1); a currency `core.money` cannot represent is kept too;
- `amount_micros` / `amount_paid_micros` — the economic amount in micros of US dollars, or **null** where
  the policy does not admit the source currency. There is no FX, so there is no dollar amount to state:
  null is "cannot be known", never zero.

A `CHECK` on each mirror table pairs the two (an economic amount exactly when the source currency is US
dollars), so the database refuses a relabel. The row is keyed on Stripe's id, so a retried event, a
second event about the same object, the poll sync and the poller's repair all meet one row and restate
it from the same reading.

**Excluded from every aggregate.** `RevenueService.accruing` selects only admitted subscriptions, and
every figure built on it — the one economic query's revenue and margin, the business margin rollup, and
the alerting snapshot an unprofitable flag is raised on — leaves the foreign ones out. Invoices are
summed nowhere.

**Visible as an exact count.** Each of those reads publishes `foreign_currency_subscription_count`:
required, never null, scoped exactly like the figures it qualifies, and 0 where nothing was left out
(the owner's ruling 5). A question that asked for no revenue left nothing out and reads 0. The
console says it beside every revenue figure it draws.

### 8. Every outbound money call reads its currency off the record it draws on (#565)

A call that wrote `"usd"` itself would send the right word today and go on sending it the day a record
said otherwise. So every outbound money call takes its currency from the authoritative monetary object
and asks `core.currency_policy.the_rails_currency`, which refuses — never reconciles — a record the
policy does not admit, or another record the same amount is drawn against that disagrees:

| Call | The record it reads |
|---|---|
| Top-up Checkout, the off-session charge, the receipt's invoice item | the wallet the top-up credits (one not yet born: the one rule it will be born by) |
| Postpaid usage invoice items | the usage invoice row; on the consolidated path the subscription's renewal draft must agree |
| The platform fee's invoice item | the billing period, which now states its currency |
| A plan's Stripe Prices, and a repriced version | the tenant, whose catalog the plan is |

The database already holds every one of those records to US dollars, so the refusal never fires on a
record UBB wrote. It is the rail proving the invariant rather than assuming it, which is why each call
asks on its own and why the tests lift the record's `CHECK` before asking. A refusal is a
`CurrencyDisagreement` — a `StripeFatalError`, raised before anything is sent.

## What proves it

| Rule | Test |
|---|---|
| §2 — the policy's answers, and that it is a policy over the table, never in place of it | `ubb-platform/core/tests/test_currency_policy.py` — `test_us_dollars_in_any_spelling_are_admitted_in_the_stored_one`, `test_anything_else_is_refused_by_name`, `test_the_policy_is_over_the_representation_table_never_in_place_of_it`, `test_the_policy_reads_no_table` |
| §3 — the tenant door | `ubb-platform/api/v1/tests/test_tenant_endpoints.py` — `TenantConfigCurrencyTest`: `test_a_currency_ubb_can_represent_is_still_refused`, `test_a_currency_ubb_cannot_represent_is_refused_the_same_way`, `test_a_refused_patch_changes_nothing_else` |
| §3 — the recording routes, single and batch | `ubb-platform/api/v1/tests/test_metering_endpoints.py` — `RecordUsageCurrencyTest`: `test_another_currency_returns_422_and_records_nothing`, `test_batch_item_in_another_currency_is_refused_by_itself` |
| §3 — a Cost Book, a reported cost's pinned code, supplied revenue | `ubb-platform/api/v1/tests/test_book_crud.py` — `test_create_book_in_another_currency_returns_422`; `ubb-platform/apps/platform/event_types/tests/test_reported_cost_mapping.py` — `test_a_fixed_currency_ubb_can_represent_and_does_not_admit_is_refused`; `ubb-platform/api/v1/tests/test_a_tenant_may_supply_the_revenue_ubb_cannot_see.py` |
| §4 — every currency column carries the `CHECK` or is a declared source fact, and nothing else | `ubb-platform/apps/platform/tests/test_v1_is_usd_only.py` — `EveryCurrencyColumnIsAccountedForTest` |
| §4 — the database refuses another currency through every door, naming its `CHECK` | same module — `TheDatabaseRefusesAnotherCurrencyThroughEveryDoorTest`: `test_no_row_is_born_in_another_currency`, `test_no_row_is_moved_into_another_currency`; `ATenantIsRefusedByTheDomainRuleBeforeTheDatabaseTest` |
| §4 — the reconciliation refuses and rewrites nothing, through the executor | same module — `TheMigrationsReconcileByRefusingTest` |
| §5 — the lock's own cases answer by the policy alone | `ubb-platform/api/v1/tests/test_tenant_endpoints.py` — `test_holding_money_changes_neither_answer` |
| §7 — kept as Stripe sent it, never relabelled, idempotent across retries, a second event, the sync and the repair, on both paths | `ubb-platform/api/v1/tests/test_a_foreign_currency_fact_is_kept_and_quarantined.py` — `AForeignSubscriptionIsKeptAndQuarantinedTest`: `test_it_is_kept_exactly_as_stripe_stated_it`, `test_a_currency_ubb_cannot_represent_is_kept_too_never_refused`, `test_a_retry_another_event_and_the_poll_sync_add_no_second_fact`; `AForeignInvoiceIsKeptAndQuarantinedTest`: `test_a_retry_a_second_event_and_the_poller_repair_add_no_second_fact` |
| §7 — absent from every aggregate, and counted on every revenue and margin read, 0 never null | same module — `test_it_is_absent_from_revenue_and_the_answer_counts_it`, `test_a_question_that_asks_no_revenue_left_nothing_out`, `test_a_tenant_with_no_foreign_subscription_reads_zero_never_null`; `TheMarginReadsCountWhatTheyLeftOutTest`: `test_the_business_rollup_counts_its_seats_and_its_own`, `test_a_rollup_that_left_nothing_out_reads_zero`, `test_the_unprofitable_list_carries_the_count_its_flag_was_raised_on` |
| §7 — the migration recovers Stripe's integer and refuses rather than rounds | `ubb-platform/apps/subscriptions/tests/test_the_mirror_keeps_what_stripe_sent.py` — `TheMigrationRecoversWhatStripeSentTest` |
| §8 — each outbound call reads its record and refuses a disagreement on its own | `ubb-platform/api/v1/tests/test_every_outbound_money_call_reads_its_records_currency.py` — `ATopUpReadsTheWalletItCreditsTest`, `APlatformFeeReadsItsBillingPeriodTest`, `APlanPriceReadsTheTenantsCatalogTest`; `ubb-platform/apps/billing/invoicing/tests/test_postpaid_consolidation.py` — `test_a_renewal_draft_in_another_currency_is_refused`, `test_a_usage_invoice_in_another_currency_is_refused`; `ubb-platform/apps/subscriptions/orchestration/tests/test_plan_versioning.py` — `test_a_new_price_version_reads_the_tenants_currency_and_refuses_another` |
| §6 — a foreign sample reaches the recording and is refused there | `ubb-platform/api/v1/tests/test_verifying_a_blueprint.py` — `test_a_foreign_currency_sample_is_the_recordings_refusal`; `ubb-platform/apps/platform/event_types/tests/test_reported_cost.py` — `test_a_supplier_returned_currency_is_represented_here_and_admitted_at_the_door` |

## Consequences

- **A second currency is an FX decision.** It needs a rate source, a policy for rate movement and an
  answer for which rate a historical period uses. That is the work #142 and #145 declined, and an
  ADR superseding this one is where it starts.
- **Every new currency column must answer the inventory.** It carries the `CHECK` or is declared a
  source fact on its model; `test_v1_is_usd_only.py` goes red otherwise.
- **`SUPPORTED_CURRENCIES` keeps its name and its eighteen entries.** It is read as "what UBB can
  represent", and its comments say so.
