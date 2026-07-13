# Referrals

The referrals product — attribute referred customers to referrers and accrue rewards from the
referred customer's usage. Code anchors are relative to `ubb-platform/`.

## Program

**Referral program**:
A tenant's single (one-per-tenant) referral scheme configuration — reward type/value, attribution
and reward windows, caps, and fraud limits. (`apps/referrals/models.py:ReferralProgram`)

**Reward type**:
How a reward is computed — `flat_fee` (fixed, paid once), `revenue_share` (fraction of referred
spend), or `profit_share` (fraction of spend minus provider cost).
(`apps/referrals/models.py:REWARD_TYPE_CHOICES`)

**Attribution window**:
How long a referral link stays valid for attribution, measured from referrer creation.

**Reward window**:
How long a referrer keeps earning from a given referral (`null` = forever).

**Max reward**:
An optional per-referral cap on total lifetime earnings.

## Actors & the referral

**Referrer**:
A customer registered to make referrals, identified by a referral code and a link token.
(`apps/referrals/models.py:Referrer`)

**Referral code**:
The human-shareable referrer identifier, of form `REF-XXXXXXXX`.

**Referred customer**:
The customer brought in by a referrer; a customer can be referred at most once per tenant.
_Avoid_: "referee" — the code says "referred customer".

**Referral**:
A single referrer → referred-customer relationship that snapshots the program's reward config at
creation, so later program edits don't change it retroactively.
(`apps/referrals/models.py:Referral`)

**Attribution**:
Binding a referred customer to a referrer via code or link token, after self-referral, duplicate,
window, and fraud checks pass.

**Referral status**:
`active`, `expired` (past its reward window), or `revoked` (manually cancelled).

## Rewards & accounting

**Reward**:
The micro-denominated amount a referrer earns from a referred customer's usage event.

**Reward accumulator**:
The one-per-referral running total of earnings, referred spend, and event count, updated in real
time. (`apps/referrals/rewards/models.py:ReferralRewardAccumulator`)

**Reward ledger**:
The immutable, per-period reward record written by batch reconciliation.
(`apps/referrals/rewards/models.py:ReferralRewardLedger`)

**Reconciliation**:
The batch re-computation of a referral's rewards from source metering data for a period, correcting
ledger and accumulator drift.

**Referred spend**:
The cumulative billed cost the referred customer has generated.

**Payout threshold**:
The minimum unpaid balance ($1 / 1,000,000 micros) a referral must exceed before a payout-due event
fires.

## Fraud

**Velocity limit**:
A cap on how many referrals a single referrer may create per day (HTTP 429 when exceeded).

**Minimum customer age**:
A rule rejecting attribution when the referred customer account is younger than a configured age.

## Events

Consumes `usage.recorded` (accrues rewards); emits `referral.created`, `referral.reward_earned`,
`referral.expired`, `referral.payout_due`.
