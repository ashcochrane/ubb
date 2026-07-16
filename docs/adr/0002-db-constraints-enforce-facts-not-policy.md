---
status: accepted
---

# Database constraints enforce accounting facts, never spend policy

`Wallet.balance_micros` has no floor CHECK — deliberately. Database constraints in the wallet
enforce **accounting facts**, invariants no business situation can make false: exactly-once
billing (`uq_wallet_txn_idempotency`, the `usage_deduction:{usage_event_id}` keys) and grant
conservation (`ck_grant_remaining_bounds`, allocation bounds). **Spend policy** — the wallet
floor (min balance), run/task caps — is never expressed as a constraint, because under the
one-rule model ([#10](https://github.com/ashcochrane/ubb/issues/10)) every usage event that
reaches UBB is priced, recorded, and billed immediately, including past the floor: the balance
must show reality, negative included. A floor constraint would make the database reject the
breaching debit — refusing to record work that already happened — which corrupts the ledger the
model exists to keep true. Same pattern as bank ledgers: overdrafts are recorded, never refused;
the limit triggers reactions, not rejection.

## Considered options

Rejected for the floor: a CHECK against a denormalized per-wallet floor column, a trigger, and a
deferred constraint. All share the fatal semantics above, and the floor is per-customer mutable
config (`CustomerBillingProfile.min_balance_micros`), so any static form also needs
denormalization + sync machinery on the hot billing path.

## Consequences

- Floor integrity rests on crossing detection + signals, the hourly reconciles, and test pins —
  a design choice, not a hardening gap. The guarantee-legibility artifact states this principle
  (decided in [#13](https://github.com/ashcochrane/ubb/issues/13)).
- Do not "harden" the wallet with a floor constraint later; that reopens
  [#10](https://github.com/ashcochrane/ubb/issues/10). A test pin (a below-floor event still
  lands and bills) ships with the one-rule spec
  ([#18](https://github.com/ashcochrane/ubb/issues/18)).
- `balance_micros` is a cached running total of `WalletTransaction`; the DB does not force them
  equal. The launch proof plan ([#15](https://github.com/ashcochrane/ubb/issues/15)) asserts
  exact agreement (hard pass/fail) after the load storm and the soak.
