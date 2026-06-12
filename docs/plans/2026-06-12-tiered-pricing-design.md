# Tiered Pricing — Graduated + Package on Price Cards (F4.1)

Date: 2026-06-12
Status: implemented (this document describes the shipped design)

## Why marginal cumulative rating

UBB prices every event at the `record_usage` choke point (record-time, not
close-time), events are immutable, and prepaid drawdown debits the record-time
amount exactly-once. Tiered pricing therefore has to be **incrementally
exact**: every tiered model is defined as a cumulative closed form `T(q)` and
each event is priced as the marginal difference

```
amount(event) = T(prior_units + units) - T(prior_units)
```

Marginals telescope, so for ANY split of a period's usage into events:

```
Σ event amounts == T(period total)        (EXACTLY, in integer micros)
```

Invoices (Σ billed of immutable events), wallets (Σ exactly-once drawdowns of
the same amounts) and the closed form always agree — no close-time re-rating,
no retro-repricing of already-debited events.

## T(q) definitions

Both are price-card only (`card_type="price"`). Cost cards stay
per_unit/flat — a tiered cost card is rejected by `validate_tiers` at the API
and, defensively, by a `PricingError` in the engine's cost loop.

### graduated

`tiers` is a non-empty list (≤ 20) of bands
`{"up_to": int>0 | None, "rate_per_unit_micros": int>=0, "unit_quantity":
int>0 (default 1_000_000), "flat_micros": int>=0 (default 0)}` with strictly
increasing `up_to` and exactly the last band unbounded (`up_to=None`).

```
T(q) = Σ over bands with lower < q of:
         band.flat_micros                                   (band entered)
       + (units_in_band * rate_per_unit_micros + uq // 2) // uq
where units_in_band = min(q, up_to) - lower,  uq = unit_quantity
```

The division is the same half-up integer division used by `compute()` for
per_unit cards. `flat_micros` is charged when the period ladder first ENTERS
the band — i.e. it appears in the marginal of the event that crosses the
band's lower bound.

### package

`tiers == []`; the card's scalar fields are reused: `rate_per_unit_micros` =
price per block, `unit_quantity` = block size, `fixed_micros` = one-time
period fee.

```
T(0) = 0
T(q > 0) = ceil(q / unit_quantity) * rate_per_unit_micros + fixed_micros
```

Consequence of marginal rating: an event that stays inside an
already-purchased block bills **0** — correct, the block was already bought;
the period sum is exact.

## Volume pricing is DEFERRED (deliberately)

Volume pricing (re-rate the WHOLE period quantity at the band the total has
reached) is not incrementally stable: crossing a band boundary changes the
price of units that were already billed and already debited from a prepaid
wallet. Supporting it would require close-time re-rating or compensating
ledger entries — both violate the record-time/immutable-event/exactly-once
drawdown invariants. It is explicitly deferred, not forgotten.

## The period counter (the ladder)

`PricingPeriodCounter(tenant, customer, lineage_id, metric_name, currency,
period_start, period_end, units_total)` with
`UniqueConstraint(tenant, customer, lineage_id, period_start)`.

- **Keyed on `lineage_id`, not metric_name**: customer overrides, dimensional
  variants and card versions each resolve to a different lineage, so each gets
  its own independent ladder; a version bump (PUT) keeps the SAME lineage_id,
  so the ladder — and marginal continuity — carries across mid-period price
  changes (`amount = T_new(prior + u) - T_new(prior)` after the change).
- **Period**: calendar month, UTC, of the record-time `as_of`
  (`tier_counter_service.month_bounds`). Once F4.2 (backdated effective_at)
  lands, the counter period will key on the effective month instead — noted
  here so the interplay is explicit.
- **Locking**: `TierCounterService.lock_and_advance` get-or-creates the row
  (create inside a savepoint + `except IntegrityError` — the
  billing/handlers.py pattern), then `select_for_update().get(...)`, reads
  `prior`, writes `prior + units`. It asserts `connection.in_atomic_block`:
  the row lock and the advance must commit or roll back WITH the caller's
  UsageEvent insert.
- **Deadlock freedom**: the engine's price loop iterates
  `sorted(usage_metrics.items())`, so concurrent events that touch several
  tiered metrics always acquire counter locks in the same order.

## record_usage restructure (the critical bit)

`PricingService.price(...)` moved INSIDE the inner savepoint of
`UsageService.record_usage`, before run-cost accumulation and the event
create. A raced duplicate insert (IntegrityError on the idempotency
constraint) now rolls back the counter advance and run accumulation with the
savepoint — replay can never double-advance the ladder. The handler was
hardened: `.filter(...).first()` and **re-raise** when no duplicate exists, so
a counter/run-machinery IntegrityError surfaces attributably instead of
masking as a replay (the old unconditional `.get()` would have raised
DoesNotExist). The fast-path idempotency pre-check is unchanged. PricingError
still maps to the same external 422 with nothing persisted.

## Provenance

Tiered price entries in `pricing_provenance["metrics"]` gain a
`tier_breakdown`: `prior_units`, `units_total_after`,
`cumulative_before_micros`, `cumulative_after_micros`, `period_start` (ISO),
`lineage_id`, and `bands` — only the bands THIS event touched, decomposed as
per-band cumulative differences so the band `micros` sum EXACTLY to the
entry's `micros`.

## Re-rate tripwire

`apps.metering.pricing.tasks.verify_tier_rerate` (beat: 1st 03:15 UTC, after
the 1st 02:00 postpaid close) re-checks every counter of the just-closed
month against the immutable event stream: (a) counter total == Σ event units,
(b) prior/after chain continuity from 0, (c) for single-card-version periods,
Σ micros == `compute_cumulative(Σ units)`. Drift → `pricing.tier_rerate_drift`
error log. ALERT ONLY — the task never mutates.

## Policies / open questions

- **Ladders are per-seat.** The counter is keyed on the event's customer
  (seat), not the billing owner — control and attribution stay per-seat
  (Stage E principle). Whether a pooled business should share ONE ladder
  across its seats (pooled tier progression) is an open product question;
  pooled money (drawdown of the marginal amounts) already works unchanged.
- **Mid-period customer-override card starts a FRESH ladder.** A new override
  card is a new lineage ⇒ prior = 0 ⇒ fresh terms from that point. Documented
  behavior: the override's ladder does not inherit the tenant-default ladder's
  progress (and vice versa when the override is deleted).
- **flat_micros on band entry** (not on first unit of the period) — the
  marginal of the crossing event carries it; see T(q) above.
- **Backfill interplay (F4.2)**: counter period keys on record-time today;
  switches to effective-month when backdated recording lands.
