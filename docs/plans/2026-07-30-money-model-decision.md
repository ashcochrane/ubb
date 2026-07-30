# The money model — what carries currency, what rounds where, and the precision guarantee

**Resolves:** [#142](https://github.com/ashcochrane/ubb/issues/142) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-30
**Decided against:** `main` @ `b0660b9`
**Builds on:** `docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — markup never
applies to a fixed price; the COGS ceiling defaults to a tenant-set fraction of the price; the
platform fee applies to the fixed-price posting.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — unknown revenue is not zero.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138, #139, #140 and #141: #154 is the single naming
pass that fixes every term once, and this document introduces a helper, a carry-forward record, a
quarantine flag and a field whose current name (`default_currency`) becomes a lie. The ADR is owed
*after* #154 and should cite all five decision documents.

---

## The decision in one paragraph

**A tenant has exactly one currency, chosen once and frozen; money is exact whole micros everywhere
inside UBB, and the currency's minor unit is reached exactly once, on the way out, with the
remainder always carried.** Currency stops being a column on ten tables and becomes a single fact on
the tenant — the two Stripe-mirrored columns survive, because they record what Stripe *reported*
rather than what we chose, and a mirror in a foreign currency is quarantined rather than summed. The
five-condition probe that guarded currency changes is deleted, not extended: it was an allowlist
that already leaked, and it could never cover the denominated values that carry no currency column
at all. Rounding gets one rule with one deliberate exception — a percentage that produces a *charge*
rounds half-up, a percentage that produces a *ceiling* rounds down, so a limit binds no later than
its exact value. Micros bind the line total, never the rate: because a rate is quantity-scaled, any
per-unit price down to 10⁻¹⁸ of a currency unit is expressible exactly, and the one real cost — a
price line under half a micro charges nothing — is accepted and surfaced at the moment a tenant sets
such a rate, rather than discovered at month end.

---

## 1. The ticket's premise, corrected

The ticket states that a task's totals "sum across events of any currency and race a currency-less
limit against them". **Through the API this cannot happen.** Every door already forces one currency:

| Door | Rule today | Evidence |
|---|---|---|
| Sync usage recording | caller currency ≠ tenant currency → `ValueError` | `usage_service.py:534-545` |
| Async ingest | same, per item → `validation_error` | `ingest_accept.py:424, 445-448` |
| Rate + book creation | same → 422 | `metering_endpoints.py:684-700` |
| Wallet creation | born in the tenant's currency | `locking.py:55-59` |
| Usage invoice | takes the tenant's currency | `postpaid_service.py:116, 277` |
| Stripe Price provisioning | takes the tenant's currency; refuses if unset | `orchestration/service.py:136, 184-187` |
| `Plan` | has **no** currency field at all | `plans/models.py` |

Every `UsageEvent.currency` is stamped from `Tenant.default_currency` (`usage_service.py:25-29`,
`:318`). So a task summing events of mixed currency is unreachable by any caller.

**The defect is real, but it is one door further back.** `_currency_locked_reason`
(`tenant_endpoints.py:470-503`) pins the currency once money exists — via a five-item allowlist:
wallet transactions, plans with provisioned Stripe Prices, pushed usage invoices, Stripe
subscriptions, active rates. **Usage events are not on it.** So:

> A tenant with `products=["metering"]`, `billing_mode="meter_only"`, markup-only pricing (no `Rate`
> rows), and no wallet can `PATCH /tenant/config {"default_currency": ...}` after ten million events.
> All five conditions read false. New events stamp the new currency, old events keep the old, and
> `Task.total_provider_cost_micros`, `Task.total_billed_cost_micros` and every analytics sum add them
> together.

That is exactly the mixed-currency sum the ticket describes — reachable today, and caused by the
lock rather than by `Task`.

**And the allowlist can never be completed**, because most denominated values carry no currency
column to key an allowlist on. A currency change silently re-denominates all of these:

| Value | Where |
|---|---|
| `RiskConfig.default_task_provider_cost_limit_micros` | billing gating config |
| `BillingTenantConfig.min_balance_micros`, `soft_min_balance_micros` | billing config |
| `ProductFeeConfig` flat `amount_micros` | tenant billing |
| `TenantMarkup.fixed_uplift_micros`, `Plan.fixed_uplift_micros` | pricing / plans |
| `Task.provider_cost_limit_micros`, both task totals | kernel |
| `TaskType`-level ceilings (#139/#140) | kernel, once built |
| `CustomerRevenueProfile.recurring_amount_micros` | subscriptions economics |

Adding usage events to the list fixes the reported path and leaves this class untouched. That is why
§2 deletes the probe rather than extending it.

---

## 2. One currency per tenant, chosen once, then frozen

### 2.1 The ruling

**A tenant is single-currency. A customer is not independently denominated.** A tenant needing to
bill in a second currency uses a second tenant.

This is what the code already does; the re-model makes it *structural* rather than seven guards that
each have to remember. Multi-currency was considered and rejected on the same evidence: the wallet,
the usage invoice, the price book, the plan and the platform fee are all tenant-scoped and would each
need a per-currency dimension, and cross-customer totals — tenant revenue, margin, platform fee —
could no longer be summed without an FX story the product deliberately does not have.

### 2.2 Chosen once

`Tenant.default_currency` stops defaulting to `usd` and becomes **unset** until chosen. Setting it is
a **one-way door**: null → value is allowed exactly once; any subsequent change is refused
unconditionally.

**`_currency_locked_reason` and its five conditions are deleted.** There is no probe, because there
is nothing to probe: the answer is always "no".

**Nothing carrying a money amount may be written until it is set.** Any write that stores, sums or
races a micros value refuses with a typed `currency_not_set` error: usage recording (both lanes),
rate and book creation, wallet creation and top-up, plan creation and provisioning, task start,
subscription provisioning, spend-limit and floor configuration. Creating a tenant, a customer, an API
key, a dimension definition or an event-type registration does not require it.

**Migration:** every existing tenant has its current value written explicitly (`usd` unless already
set), so no live tenant is stranded and no behaviour changes for them. Sandbox clones already copy
the parent's value (`sandbox_service.py:44`) and continue to.

**Onboarding consequence:** there is no self-serve tenant-creation endpoint — tenants are created
operator-side and currency is only settable afterwards via `PATCH /tenant/config`. So currency
selection must appear in the console's first-run path, or the operator must set it at creation.
Without one of those, a new tenant is blocked from every money write. **This is a hard prerequisite,
not a nicety**, and belongs in the cutover sequence (#155).

### 2.3 Why one-way and not "while nothing is denominated"

The escape hatch is worth almost nothing and costs the invariant. A tenant reaches the point of
having denominated *something* within minutes of starting — one rate card, one event, one wallet. In
exchange for that narrow window, every future money field has to remember to join an allowlist, and
§1 shows the allowlist is already incomplete in a way no reviewer would spot. A mis-set currency
before any use is an operator correction, not an API affordance.

---

## 3. Where currency lives: ten columns become two

### 3.1 The inventory

Eleven places store a currency today — the tenant's, plus ten copies.

| # | Column | Source today | Becomes |
|---|---|---|---|
| — | `Tenant.default_currency` (`tenants/models.py:70`) | the tenant chooses | **the only stored currency** |
| 1 | `UsageEvent.currency` (`usage/models.py:23`) | stamped from tenant | **deleted** |
| 2 | `Rate.currency` (`pricing/models.py:85`) | 422 unless it matches | **deleted** |
| 3 | `RateCard.currency` (`pricing/models.py:143`) | 422 unless it matches | **deleted** |
| 4 | `RateCardAssignment.currency` (`pricing/models.py:172`) | copied from the book | **deleted** |
| 5 | `Wallet.currency` (`wallets/models.py:29`) | born from tenant | **deleted** |
| 6 | `CreditGrant.currency` (`wallets/models.py:167`) | copied from wallet (`grants.py:199`) | **deleted** |
| 7 | `CustomerUsageInvoice.currency` (`invoicing/models.py:68`) | copied from tenant | **deleted** |
| 8 | `CustomerRevenueProfile.currency` (`economics/models.py:58`) | tenant-declared external revenue | **deleted** |
| 9 | `StripeSubscription.currency` (`subscriptions/models.py:29`) | **whatever Stripe reported** | **survives** |
| 10 | `SubscriptionInvoice.currency` (`subscriptions/models.py:66`) | **whatever Stripe reported** | **survives** |

Eight go; two survive. The line is not "internal versus external" — it is **chosen versus
observed**. Rows 1–8 are copies of a decision UBB made and can never legitimately differ. Rows 9–10
record a fact that originated outside UBB and *can* differ (§4).

### 3.2 Two constraints go with them

Both encode a multi-currency capability the system refuses to provide:

- `uq_assignment_customer_currency` — `UNIQUE(tenant, customer, currency)`
  (`pricing/models.py:176-179`). Promises "one price book per customer **per currency**". The second
  row is unreachable. Becomes `UNIQUE(tenant, customer)`.
- `uq_ratecard_one_default_per_provider` — `UNIQUE(tenant, card_type, provider_key, currency)` where
  `is_default` (`pricing/models.py:154-157`). Same shape; loses `currency`.
- `uq_rate_active_in_book` (`pricing/models.py:101-106`) carries `currency` among fourteen fields;
  it drops out of the key.

Removing these is not cosmetic. A constraint that promises a capability the code rejects is a
standing invitation to build against it.

### 3.3 The wire contract does not change

**Deleting the column does not delete the field.** `currency` stays in every API response that
carries it today — event reads, wallet reads, book and rate reads, invoice reads — served from the
tenant. Clients see no difference, `openapi/v1.json` is unaffected for those paths, and no
deprecation applies. The only contract-visible change is on `PATCH /tenant/config`, where
`default_currency` becomes settable once rather than conditionally (§2.2), and on rate/book creation,
where an explicit `currency` that matches is accepted-and-ignored rather than validated. Whether the
request field survives at all is a #155 cutover call.

### 3.4 The name

Under this ruling `default_currency` is actively misleading — nothing else can override a default
that cannot vary. **Recommended rename: `Tenant.currency`.** Handed to #154 with the rest of the
vocabulary, not done here, so the naming pass stays one pass.

---

## 4. The one exception: the Stripe mirror

### 4.1 Why it is different

`StripeSubscription.currency` is taken verbatim from Stripe (`stripe/sync.py:83`,
`api/webhooks.py:44`) and nothing compares it to the tenant's. UBB provisions its own Prices in the
tenant's currency, but **a tenant can create subscriptions directly in their own connected Stripe
account**, and UBB mirrors those too. `_currency_locked_reason`'s own docstring concedes the gap:
the currency of a provisioned Stripe Price is not stored locally, so a cross-check is impossible.

Today a foreign-currency subscription is recorded and its `amount_paid_micros` is summed into
revenue and margin with no currency filter (`subscriptions/queries.py:38-41`) — a number wrong by
whatever the exchange rate happens to be, presented as fact.

### 4.2 The rule: mirror, flag, exclude

**A mirrored subscription or invoice whose currency is not the tenant's is recorded, flagged, and
excluded from every money aggregate until resolved.** It appears as a named exception the tenant can
act on; it never contributes to revenue, margin, usage-billed or platform-fee totals.

This follows two rulings already made:

- **#138's quarantine precedent** — unknown event types are quarantined and replayed, never
  auto-registered. The parallel is exact: record that something exists, refuse to interpret it.
- **#141's rule that unknown revenue is not zero** — which is precisely why "refuse to mirror it" was
  rejected. Dropping the row makes the subscription's revenue read as a confident zero, the failure
  mode #141 called out.

Converting was rejected for the reason multi-currency was: it requires an FX rate source, a policy
for rate movement, and a story for which rate applies to a historical period — all invented to serve
a case the single-currency ruling exists to prevent.

### 4.3 What "excluded" must mean concretely

Every aggregate over `StripeSubscription.amount_micros` or `SubscriptionInvoice.amount_paid_micros`
filters the flag out **and reports the excluded count** — a silent exclusion is the same lie as a
silent inclusion, one decimal place quieter. Handed to #153 (analytics) and #152 (dashboard).

---

## 5. Rounding

### 5.1 The six sites today

| # | Where | Rule | Evidence |
|---|---|---|---|
| 1 | each priced line | half-up to whole micros | `pricing/models.py:123-127` |
| 2 | markup, when no price line matched | half-up on the event's provider cost, plus a fixed uplift | `pricing/models.py:32-34`, `pricing_service.py:162-167` |
| 3 | platform fee, per period | floor to whole cents, **remainder dropped** | `tenant_billing/services.py:102, 122` |
| 4 | usage-invoice lines pushed to Stripe | floor to cents, **remainder carried** into the next line, then banked for the next period | `postpaid_service.py:292-302` |
| 5 | the Stripe boundary | refuses anything not already whole cents | `stripe_service.py:28-37` |
| 6 | prepaid wallet drawdown | none — micros end to end | `wallets/` |

Sites 3 and 4 disagree, and none of it is written down anywhere.

Note also what site 2 is *not*: markup does not stack on a matched price line, it is the **fallback**
when none matched (`pricing_service.py:162-167`) — so cost-then-markup-then-price never composes
into a chain of three roundings.

### 5.2 The rule

**R1 — a computed price line rounds half-up to whole micros, at the moment it is computed.**
`Rate.compute` is unchanged. This runs once per (event × metric), on both the cost and the price side.

**R2 — everything downstream is exact.** Every amount stored, summed, compared against a limit, held,
reserved or drawn from a wallet is an exact whole number of micros. No rounding happens anywhere
between R1 and R3.

**R3 — the currency's minor unit is reached exactly once, at the money boundary, and the remainder is
always carried.** Never dropped, never truncated away. This is what usage invoices already do
(`PostpaidResidualLedger`); the platform fee changes to match, gaining an equivalent carry-forward
record.

**R4 — a percentage that produces a *charge* rounds half-up; a percentage that produces a *ceiling*
rounds down.** So #139's COGS ceiling — a tenant-set fraction of the fixed price — binds no later
than its exact value. A ceiling that rounds up would let a job burn marginally more than the tenant
declared, which is the one direction a spend control must never err.

### 5.3 Why R1 stays per line

Per-event and per-invoice rounding were both considered.

**Per event** — keep each metric's fraction, sum, round once — costs the receipt. The per-metric
`micros` entries in `pricing_provenance` (`pricing_service.py:136-160`) currently add up exactly to
`billed_cost_micros`. Under per-event rounding they would not, and that receipt is what #138's
pricing model leans on to explain a charge.

**Per invoice** — store exact fractions on events, round at the bill — ends whole-number money. The
wallet ledger, the live spend counter, every limit comparison and every exactly-once money proof in
the suite are integer arithmetic. The accuracy bought does not approach the cost: the worst case per
line is **half a micro, i.e. one twenty-thousandth of a cent**. Twenty thousand lines would have to
err in the same direction to be a single cent out, and half-up is unbiased except at exact halves.

### 5.4 What R3 does and does not touch

- **Inward boundaries stay.** Top-up and checkout amounts must still be whole minor units
  (`schemas.py:289, 305, 329, 466`, `me_endpoints.py:82`) — that is money Stripe will really move.
- **`micros_to_cents` keeps refusing** non-aligned amounts (`stripe_service.py:28-37`). Under R3 it
  is an assertion that the carry logic ran, not a conversion policy.
- **A fixed price (#139) needs no alignment.** For a prepaid tenant it is drawn in micros and never
  becomes its own Stripe amount; for a postpaid tenant it enters an invoice line and takes the
  floor-with-carry like any other line. Requiring tenants to state cent-aligned fixed prices would be
  a restriction with no cause.
- **Prepaid drawdown still never rounds.** A prepaid balance may hold sub-cent value indefinitely;
  it is only ever converted if it leaves via Stripe.

---

## 6. Precision — the guarantee

### 6.1 Micros bind the line total, not the rate

The ticket asks whether micros can express a per-token price far below a micro. **They can, and the
mechanism already exists and is already exposed.** A rate is quantity-scaled:

```
line = (units × rate_per_unit_micros + unit_quantity // 2) // unit_quantity + fixed_micros
```

`unit_quantity` is a caller-set `BigIntegerField` (`pricing/models.py:83`), exposed on the API with
`gt=0` and a default of 1,000,000 (`schemas.py:775`, `metering_endpoints.py:807`). So $0.25 per
million tokens is `rate_per_unit_micros=250_000, unit_quantity=1_000_000` — exactly 0.25 micros per
token, stored exactly, with no representation error at all.

**The smallest expressible per-unit price** is therefore bounded by `unit_quantity`'s range, not by
micros: `rate_per_unit_micros=1` with `unit_quantity=10¹²` is 10⁻¹⁸ of a currency unit per unit.

### 6.2 The guarantee, in publishable form

1. **Unit.** All money is an integer number of micros; one micro is 10⁻⁶ of a currency unit.
2. **Quantities are non-negative integers** on both ingest lanes — `dict[str, int]`
   (`schemas.py:71`), inherited by the async lane via `IngestEventIn(RecordUsageRequest)`
   (`schemas.py:116`). No floating-point value enters money arithmetic at any point.
3. **Rate precision is not limited by micros.** Any per-unit price down to ~10⁻¹⁸ of a currency unit
   is expressible exactly, via `unit_quantity`.
4. **Range.** ±9.22 × 10¹⁸ micros ≈ ±9.2 trillion currency units, per `BigIntegerField`.
5. **Maximum loss per price line: under half a micro** (one twenty-thousandth of a cent), from R1.
6. **Maximum loss per bill: zero.** The minor-unit remainder is carried, never dropped (R3).
7. **A line computing to less than half a micro charges nothing** (§6.3).

### 6.3 The sub-micro line, and why it is accepted

R1's floor has one real consequence: a line under half a micro rounds to zero. The same usage can
therefore earn differently depending only on how it was batched — a million calls priced at 0.4
micros each earn nothing as a million events, and 400,000 micros as one event of quantity 1,000,000.

**Accepted, with the trap surfaced where it is set.** Two reasons:

- The mechanism that avoids it is the one tenants already use. Real per-token pricing is quoted *per
  million tokens*, and `unit_quantity` expresses exactly that. A rate fine enough to produce
  sub-micro lines is nearly always a rate expressed at the wrong scale.
- The alternative breaks two guarantees. Carrying the sub-micro fraction forward per customer — the
  same never-drop rule one level down — makes an event's price depend on the events before it. That
  ends replay returning the same answer, ends the accept-time estimate equalling the settled price
  (`pricing_service.py:197-222`), and puts a contended per-customer row in the hot ingest path.

**Mitigation: warn at rate-set time.** When a tenant creates or reprices a rate whose single-unit
line would round to zero — `rate_per_unit_micros × 2 < unit_quantity` — the API returns the rate with
a warning naming the quantity at which the line first becomes chargeable. Not an error: a genuinely
cheap per-call price is legitimate when calls arrive in batches. Handed to #145, which owns the
quantity vocabulary this warning is phrased in.

**This directly constrains #149** (streaming: one event or many?). Splitting a long call into many
small events multiplies the number of R1 roundings and can push individual lines under the half-micro
floor. Event granularity is a pricing-accuracy decision, not only an ergonomics one.

---

## 7. The minor unit: one helper, list unchanged

### 7.1 What CUR-1 actually is

`SUPPORTED_CURRENCIES` (`tenants/models.py:21-31`) admits eighteen two-decimal currencies and rejects
zero-decimal (JPY, KRW) and three-decimal (KWD, BHD, JOD) ones. The stated reason is not a product
decision — it is that the 1/100 minor unit is hard-coded in too many places to change safely.

**Exact inventory: 20 sites across 11 files** (excluding tests, migrations, and the explanatory
comment):

| File | Sites |
|---|---|
| `api/v1/schemas.py` | 4 whole-cent validators (`:289, :305, :329, :466`) |
| `api/v1/me_endpoints.py` | 1 validator (`:82`) |
| `api/v1/webhooks.py` | 2 cents→micros (`:231, :252`) |
| `apps/billing/connectors/stripe/webhooks.py` | 3 cents→micros (`:62, :305, :424`) |
| `apps/billing/connectors/stripe/tasks.py` | 1 cents→micros (`:213`) |
| `apps/billing/stripe/services/stripe_service.py` | 1 converter, `micros_to_cents` (`:28-37`) |
| `apps/billing/invoicing/services/postpaid_service.py` | 1 conversion + 2 range guards (`:253, :297-298, :302`) |
| `apps/billing/tenant_billing/services.py` | 2 fee floors (`:102, :122`) |
| `apps/subscriptions/stripe/items.py` | 1 (`:17`) |
| `apps/subscriptions/ports.py` | 1 (`:115`) |
| `apps/subscriptions/orchestration/service.py` | 1 (`:580`) |

### 7.2 The ruling

**Fix the scatter; keep the list.** Every one of those 20 sites routes through a single helper that
asks the currency how many minor units it has. `SUPPORTED_CURRENCIES` stays exactly as it is until a
tenant actually needs yen.

The point is that the *reason* for the restriction is removed. Afterwards, admitting JPY is a
one-line data change plus a live Stripe money test in that currency — not an archaeology exercise
across eleven files. The restriction becomes a choice; today it is a constraint.

Lifting it in the same pass was rejected on evidence, not appetite: three-decimal currencies carry
Stripe's own rule that amounts must be rounded to the nearest ten minor units, and no currency class
can be trusted until it has been through the live Stripe money test the programme already owes
(map #9's deferred proof stage). Building and shipping that for a currency no tenant has asked for
spends the clean-break window on the wrong thing.

### 7.3 Shape of the helper

One module — `core/money.py` is the natural home, beside the existing `core/` primitives — owning:

- `minor_units(currency) -> int` — the multiplier (10,000 micros per minor unit for two-decimal).
- `to_minor(amount_micros, currency) -> (minor, remainder)` — the floor-with-carry of R3, returning
  the remainder rather than hiding it, so no caller can drop it by omission.
- `from_minor(amount, currency) -> micros` — the exact inbound conversion.
- `assert_aligned(amount_micros, currency)` — what `micros_to_cents` becomes: the boundary assertion
  that the carry ran.
- `round_charge(numerator, denominator)` / `round_ceiling(numerator, denominator)` — R4's two
  percentage roundings, so the difference is a named function rather than a remembered convention.

`SUPPORTED_CURRENCIES` moves next to `minor_units` — one table, one place, both facts about a
currency together.

---

## 8. Answers to the ticket's five questions

**Is a tenant single-currency, a customer single-currency, or neither? → Tenant, and the missing
`Task` currency is therefore not a bug.** A task inherits the tenant's one currency like everything
else. Once the lock is a one-way door (§2), a mixed-currency total is unreachable by any path,
config included. `Task` should **not** gain a currency column — it would be the ninth copy of a
frozen fact, one document after we deleted eight.

**If multi-currency is real: what does a task-level spend limit mean, and a fixed price? →
Moot, deliberately.** Both mean exactly what they say, in the tenant's one currency. This is the
question the ruling exists to dissolve rather than answer.

**Where should rounding happen, and is the current answer defensible when a fixed price and a markup
can both apply? → Per line, and the premise does not arise.** Per line, half-up, is defensible (§5.3)
and is kept. **A fixed price and a markup can never both apply**: #139 settled that markup is a
function of provider cost, so applying it to a fixed price would make a fixed price move with cost —
which is the one thing a fixed price is for. There is no compounding case to defend. What does change
is site 3: the platform fee stops dropping its remainder (§5.2 R3).

**Is micros still right for a per-token price far below a micro? What is the smallest price
expressible, and is it enough? → Yes; ~10⁻¹⁸ of a currency unit; yes.** Micros bind the line total,
not the rate, because `unit_quantity` is caller-set and unbounded (§6.1). The one real limit is that
a line under half a micro charges nothing — accepted, warned about at rate-set time, and handed to
#149 as a constraint on event granularity.

**Zero-decimal currencies: keep CUR-1, or does the re-model make it removable? → Keep the list,
remove the reason.** 20 sites collapse to one helper; the supported list is then a data decision
rather than an architectural one (§7).

---

## 9. What each existing thing becomes

| Thing | Today | After |
|---|---|---|
| `Tenant.default_currency` | defaults `usd`, changeable while the five conditions read false | **unset until chosen, then frozen**; rename to `currency` handed to #154 |
| `_currency_locked_reason` | five-condition allowlist | **deleted** |
| Eight derived currency columns | copies of the tenant's | **deleted**; API still serves `currency` from the tenant |
| `StripeSubscription.currency`, `SubscriptionInvoice.currency` | mirrored, silently summed | **kept**; foreign ones flagged and excluded from every aggregate |
| `uq_assignment_customer_currency` | `(tenant, customer, currency)` | `(tenant, customer)` |
| `uq_ratecard_one_default_per_provider` | includes `currency` | loses `currency` |
| `uq_rate_active_in_book` | includes `currency` | loses `currency` |
| `Rate.compute` | half-up per line | **unchanged** — now a stated rule (R1) |
| `TenantMarkup.calculate_markup_micros` | half-up | **unchanged**; expressed via `round_charge` (R4) |
| Platform fee floor | floors, **drops** the remainder | floors, **carries** it, matching usage invoices (R3) |
| `PostpaidResidualLedger` | postpaid usage only | the pattern; a sibling record appears for the platform fee |
| `micros_to_cents` | the converter | `assert_aligned` — a boundary assertion; conversion moves to `to_minor` |
| 20 hard-coded `10_000`s | scattered across 11 files | one `minor_units` table in `core/money.py` |
| `SUPPORTED_CURRENCIES` | 18 two-decimal currencies | **unchanged**, relocated beside `minor_units` |
| Rate creation | accepts any `unit_quantity` silently | warns when a single-unit line would round to zero |

---

## 10. Constraints this imposes on other tickets

- **#145 (quantity vocabulary)** — owns the noun `unit_quantity` becomes, and the wording of the
  sub-micro warning (§6.3). The "per N units" semantic is load-bearing for the precision guarantee,
  not an implementation detail to be renamed away.
- **#146 (provider-supplied cost)** — caller-supplied cost is capped at `le=999_999_999_999`
  (`schemas.py:69-70`), about 1,000,000 currency units, while a rate-card-computed cost is capped
  only by `BigIntegerField` (~9.2 trillion). That asymmetry is unexplained and belongs to #146.
- **#147 (markup)** — markup's rounding is R4's `round_charge`; and `CustomerRevenueProfile.currency`
  disappears under §3, which touches the same manual-revenue surface #147 is re-modelling.
- **#148 (historically accurate recalculation)** — reproducibility now includes rounding: a recompute
  must apply R1 identically to be byte-comparable. Deleting `Rate.currency` is safe for historical
  recompute **only because** currency is frozen (§2); if #148 wants recompute at an arbitrary
  as-of, that dependency is explicit.
- **#149 (streaming: one event or many)** — event granularity is a pricing-accuracy decision. More,
  smaller events means more R1 roundings and a real risk of sub-micro lines charging zero (§6.3).
- **#150 (spend limits re-modelled)** — "denomination" is answered: the tenant's one currency, no
  currency field, no cross-currency comparison. A percentage-derived ceiling rounds **down** (R4).
- **#152 (task dashboard) / #153 (analytics re-alignment)** — quarantined foreign-currency
  subscriptions must be **excluded and counted**, never zeroed and never silently omitted (§4.3).
- **#154 (vocabulary lock)** — names owed: `Tenant.currency` (from `default_currency`), the
  `core/money.py` helpers, the platform-fee carry record, the foreign-currency quarantine flag, and
  whether "micros" survives as the public word in API field names.
- **#155 (migration and cutover)** — eight column drops, three constraint rewrites, the
  explicit-currency backfill, and the hard prerequisite that currency selection exists in onboarding
  before the `currency_not_set` gate ships (§2.2).
- **#156 / #157 (Code Builder)** — currency is **not** a per-call input. Generated code must not emit
  a `currency` field on usage recording, and the builder's money examples should use `unit_quantity`
  at the scale prices are really quoted (per million tokens), since that is what keeps lines above
  the sub-micro floor.

---

## 11. Known residue, flagged rather than buried

- **The platform-fee carry has no home yet.** `PostpaidResidualLedger` is per customer; the fee is
  per tenant per period. A sibling record is implied but its shape — and whether an unpushed period
  can strand a carry — is not designed here.
- **`usage_metrics` values have no upper bound.** `dict[str, int]` with a non-negative validator
  (`schemas.py:71-82`) but no ceiling, so a large enough quantity × rate overflows
  `BigIntegerField` at save time rather than being refused at the edge. Small, real, unassigned.
- **Sandbox tenants never accrue platform fees** (`tenant_billing/services.py:87-88`), so the fee
  carry is a no-op for them. Harmless, but the carry record should not be created rather than created
  at zero.
- **Nothing today compares a mirrored Stripe Price's currency to the tenant's at provisioning time**
  — §4 catches the subscription after the fact. Whether provisioning should verify what Stripe
  actually created is a narrower question left to #147/#151.
- **The one-way door has no operator escape.** A tenant that sets the wrong currency and immediately
  notices needs a data fix. Deliberate (§2.3), but it should be a documented operator runbook rather
  than folklore.
