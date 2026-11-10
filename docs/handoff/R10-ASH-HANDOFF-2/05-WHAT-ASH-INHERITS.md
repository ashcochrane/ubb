PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# 05 - What Ash inherits (the register)

At `a6738e78e96ab10eabd45dc10fafdc842b7de519` the billing product carries no known BILLING BLOCKER or PRE-ASH
REQUIRED FIX. What remains is infrastructure, Stripe/environment integration, production SLO/admission work and
accountable human decisions. Each item names what it is, why UBB cannot do it alone, and where it is read from.

The three identities (`00-README.md`): behavioural proof anchor `a6738e78e96ab10eabd45dc10fafdc842b7de519`; SDK release commit
`b41b395f59d798cec83289d83d5ec71f83201c7f` (`sdk-v5.0.0`, wheel SHA-256 `56d28b90…`); current repository baseline
`90d008b709a86ff0d63588d8dd6b0a160978230b` (two documentation-only commits past the proof anchor; no billing behaviour changed).

## 0. Completed before handoff - NOT Ash's work

These are done and are listed only so they are never mistaken for inherited work:

- Stage A and Stage C1a-C5 product repair (#625, #626-#631), every Stage B finding repaired (`04`);
- Stage D billing re-proof on `a6738e78…` - BILLING BLOCKER 0, PRE-ASH REQUIRED FIX 0 (`00`, `R10-BILLING-STAGE-D-EVIDENCE/`);
- the D2 documentation clean-up (#632 → `b41b395f…`);
- the `sdk-v5.0.0` annotated tag; the reproducibly built wheel `ubb_sdk-5.0.0-py3-none-any.whl`; its clean-environment
  verification (§9, `R10-SDK-V5-RELEASE/`);
- the repository changelog release record (#633 → `90d008b7…`);
- the W7 starting-baseline refresh to `90d008b7…` (pointer only; STATUS still `PRE-LAUNCH - NOT FINAL`);
- the first-client SDK ruling: `sdk-v5.0.0` if the client integrates through the Python SDK (FINAL owner/consultant
  ruling, 2026-11-09; W7 §0.5 step 13) - the release is handed over by file from `R10-SDK-V5-RELEASE/`, not via PyPI.

Ash inherits the external/operational lane in §1-§8 below, the W7 acceptance/admission process (§6) with its accountable
human decisions and signatures, the first real tenant in `external` mode, and payment-rail activation only if and when a
money-mode tenant is later admitted (§7). §10-§12 are accepted observations and ruled non-goals, kept visible; none is a
blocker.

## 1. Infrastructure: one image, three roles, a one-off migration

The repository has no Dockerfile or deployment files (ADR-0026; the W7 preparation pass proved a draft image locally,
`R10-W7-PREP/`). W7's deployment-files PR adds one immutable image running `web` (a WSGI server over
`config/wsgi.py`), `worker` (`celery -A config worker`; nine `ubb_*` queues), `beat` (one singleton; the schedule in
`config/settings.py::CELERY_BEAT_SCHEDULE`) and `python manage.py migrate` as an explicit release operation. Managed
PostgreSQL 16 and Redis 7 in one region; secrets through the host; a log drain for JSON app lines and Celery's text;
HTTPS behind a proxy setting `X-Forwarded-Proto`; outbound HTTPS for webhooks and Stripe. The seven W7 inputs
(hosting provider/service, region, account holder, acceptance signer, the first real tenant identity, the governance
decision-maker, the alert destination) are the owner's (`R10-W7-DELIVERY-PROMPT.md`, `R10-W7-INFRA-FACTS-CHECKLIST.md`).

## 2. Stripe: credentials, Connect, receivers (R-1, R-2, R-3)

- **R-1 - Stripe test credentials, a Connect test account, a public test receiver.** Level 2 of the Stripe boundary
  ran in neither Stage B nor Stage D: no `STRIPE_TEST_SECRET_KEY`, `STRIPE_TEST_WEBHOOK_SECRET` (a real one),
  `STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET`, `STRIPE_CONNECT_TEST_CLIENT_ID`, `STRIPE_TEST_CONNECTED_ACCOUNT`, and
  no public HTTPS receiver exists. With them, `test_live_stripe_ar.py` (opt-in `UBB_STRIPE_LIVE_TEST=1`), a real
  test-mode push, a test-mode checkout/PaymentIntent and `invoice.paid` at `/api/v1/webhooks/stripe/test` become
  runnable as Level 2 (bounded: test mode only, a sandbox tenant, unique objects, no secret in evidence).
- **R-2 - rail activation, Connect onboarding, public receivers, hosting, SLOs.** A `PaymentRailActivation` row per
  environment is an accountable human act (ADR-0008 §6); a tenant's connected account comes from Connect OAuth
  (`apps/billing/connectors/stripe/connect.py`, needs `STRIPE_CONNECT_CLIENT_ID`) and `charges_enabled` from Stripe's
  `account.updated`; the two live receivers need public HTTPS endpoints registered with Stripe, each with its own
  signing secret (`STRIPE_WEBHOOK_SECRET`, `STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET`) and the event types it owns.
- **R-3 - the Stripe environment layout.** The platform assumes one platform account: `STRIPE_SECRET_KEY` live,
  `STRIPE_TEST_SECRET_KEY` for sandbox tenants, each receiver registered once per mode (PLAN §8). A single-test-key
  "all-test" layout is not supported: `livemode_filter` makes `invoice.*`/`account.*` handlers no-ops for non-sandbox
  tenants under test-mode events.

## 3. Hosting, logging drain, the dead-letter alert recipient

Application logs are JSON lines on stderr (`core/logging.py`); the worker's per-task INFO lines from `ubb.*` loggers
are dropped by the logging configuration (Stage B O-11; dispatch is proven from durable rows). The structured ERRORs
an operator must route somewhere: `live_counter.drift_spike`, `wallet.drawdown_repair_spike`,
`billing.stripe_refund_total_below_applied`, the `stripe_refund_reversed` alert (Q19),
`platform_invoice.no_platform_customer`, `subscription.mirror_ambiguous`, `seat.qty_push_failed` /
`seat.qty_reconcile_failed`, `postpaid.snapshot_divergence`, `outbox.handler_failed` (dead letters after five retries),
`clerk.rs256_backend_unavailable`. W7 input 7 names the destination.

## 4. SLO 1-3

SLO 1 (p99 ≤ 200 ms at batch sizes up to 100, measured on the real host first; a miss stops W7), SLO 2 (webhook
receipt timing at a controlled public receiver), SLO 3 (the external-mode storm). Local figures are not measurements.

## 5. Native required checks on `main`

The five CI check families (`test`, `contracts`, `contract`, `codegen`, `code-builder-execution`;
`.github/workflows/ci.yml`) are green on every merged head, but native required-check enforcement on `main` is NOT
configured; the temporary `R10-merge-guard.py` (project folder) is the recorded compensating control for the R10
merges and is not branch protection. **The repository owner applies the ruleset** (`R10-W7-REQUIRED-CHECKS-ruleset.json`,
`R10-W7-VERIFY-REQUIRED-CHECKS.py`); the guard is not a substitute and is not made permanent.

## 6. The W7 admission act

The whole of `R10-W7-DELIVERY-PROMPT.md` (STATUS `PRE-LAUNCH - NOT FINAL`): the deployment-files PR, the exact
release record and image digest, the production environment, SLO 1 first, the acceptance audit with its named
signer, the first real `external` tenant on the release image, the real-client golden path, the durable admission
record (the docs-only PR deleting the "no tenant is live" note; one comment on #540). The W7 starting baseline was
refreshed on 2026-11-09 (final transition window) to the current `main` `90d008b709a86ff0d63588d8dd6b0a160978230b` - the docs-only
#633 successor of the D2 `main` `b41b395f…` - as a pointer only; the STATUS line stays `PRE-LAUNCH - NOT FINAL` and never
carries a SHA. W7 has not been executed; it needs the seven named launch inputs and the accountable decisions first.
Native required-check enforcement (§5) is still an accepted temporary limitation; the R10 merge guard was a compensating
control for the R10 merges, not branch protection.

## 7. Rail activation

Never part of Stage B or D (Level 3). The first client is admitted `external`; converting any tenant to a money mode
needs the activation row, a charge-ready connected account, the receivers and the credentials above, and an
accountable approver named in the row.

## 8. The Clerk production environment

Member sign-in to the console in `api` mode needs `VITE_CLERK_PUBLISHABLE_KEY` on the console and `CLERK_ISSUER` plus
`CLERK_JWKS_URL` or `CLERK_JWT_PUBLIC_KEY` on the backend. **F-16 is repaired**: the lock pins the RS256 backend
(`cryptography==50.0.2`, `cffi==2.1.1`, `pycparser==3.12`) and the PEM/JWKS paths are tested in a clean environment, so
the only missing piece is the Clerk environment itself. Real-browser `api` mode was NOT EXECUTED in Stage B or D.

## 9. The `sdk-v5.0.0` release act - COMPLETED BEFORE HANDOFF (2026-11-09); NOT inherited

The repository declares 5.0.0 (`ubb-sdk/pyproject.toml`, `ubb/__init__.py`, `tests/test_release.py`, `CHANGELOG.md`,
`MIGRATION.md §27`; `SDK_MAJOR_VERSION 5` in `api/v1/integration_blueprint.py`; codegen catalogue 11). Stage D created
neither tag nor wheel; the owner's separately authorised release act (FINAL ruling 2) has since done both, on the
post-D2 `main`:

| Item | Value |
|---|---|
| Tag | `sdk-v5.0.0`, annotated (object `fbf765b7efc19c2f3b08f2313ae6e72923e4b340`), dereferencing to **`b41b395f59d798cec83289d83d5ec71f83201c7f`**; pushed as the one tag ref and verified remotely |
| Wheel | **`ubb_sdk-5.0.0-py3-none-any.whl`**, SHA-256 **`56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`** - built by the tag's own `ubb-sdk/release/build_wheel.py` (Python 3.13.14, the hashed lock, two builds, one hash) |
| Verification | wheel contents = the tag's tree (650/650 blobs); clean-venv install from the wheel file, `ubb.__version__` = metadata = `5.0.0`; `tests/test_release.py` 23 passed and the whole SDK suite 477 passed against the installed wheel; `tools/verify_sdk_v5_release.py` RELEASE EVIDENCE VALID |
| Handed over as | a release artefact in **`R10-SDK-V5-RELEASE/`** (project folder) with `sdk-v5.0.0.release.json` and the evidence files |
| **Not published** | nothing uploaded to PyPI or any index - distribution of the wheel beyond this handoff is a separate owner decision |
| Repository | unchanged; `main` = `b41b395f59d798cec83289d83d5ec71f83201c7f` throughout; no PR |

What Ash does NOT inherit here: the tagging, the build, or the repository release record — the docs-only PR #633
("SDK v5 release record: pin the released wheel SHA-256") was guard-merged on 2026-11-09 → `main` =
`90d008b709a86ff0d63588d8dd6b0a160978230b`, so `ubb-sdk/CHANGELOG.md` on `main` now carries the 5.0.0 "Release stamp" table with
the wheel and its full SHA-256, as 4.0.0's does; the tag still dereferences to `b41b395f…`. The W7 anchor refresh (§6) was
completed in the final transition window, 2026-11-09. Nothing in this section remains for Ash or the owner.

## 10. The accepted v1 operational paths (rulings, not defects)

- **A Stripe refund that later fails or is cancelled is alert-only** (RULED Q19, PLAN §7 item 19):
  `charge.refund.updated` with `failed`/`canceled` emits ONE structured ERROR (`stripe_refund_reversed`, with tenant,
  customer, owner, attempt, charge, refund ids, status, amounts, the applied sum - no secret) and leaves the wallet
  unchanged; an accountable operator verifies the Refund in Stripe and, if warranted, re-credits through
  `POST /api/v1/billing/customers/{id}/credit` with a movement reason. No automatic reversal workflow exists. Exercised
  locally in `03-prepaid-*` step 13.
- **The platform-fee Stripe customer is set by command** (RULED Q6): `manage.py set_platform_billing_customer
  --tenant <id> --stripe-customer-id cus_… [--verify] [--operator <id>]`, audited as
  `tenant.platform_billing_customer_set`; until then fee periods stay `closed` and the job reports
  `platform_invoice.no_platform_customer` once per run.
- **The manual hold is one operator command** (RULED §7 item 41): `manage.py set_customer_manual_hold --customer
  <uuid> --state held|released --operator <id>`; `status`, `suspension_reason` and `deleted_at` are read-only in the
  Django admin; closing a customer is not a supported v1 transition; the release never forces a customer active past a
  standing system cause (HANDED_OVER). Audited as `customer.manual_hold_set` / `customer.manual_hold_released`.
- **Subscription mirror rebinding is not supported in v1** (item 33): a future need is a separately designed operator
  workflow with stated economic consequences.
- **A Stripe Event older than Stripe's retention cannot be re-run** by `reprocess_webhook` (item 36's stated
  operational limit); redelivery within Stripe's retry window is the other route.

## 11. ADJACENT PRODUCT FINDINGS / OBSERVATIONS left open (truthfully recorded, none stops the paths)

Stage D found **no new ADJACENT PRODUCT FINDING**. Observations, new and carried:

| Id | Observation | Class | Where |
|---|---|---|---|
| D-O1 | `pnpm ui:api:check` (`apps/ui` `api:sync`: `API_SPEC_PATH=… bash …`) cannot run from cmd.exe on Windows; the Git Bash equivalent shows zero drift; CI runs on Ubuntu | OBSERVATION (developer experience) | `10-console-codegen.txt` |
| D-O2 | one console vitest (`customer-detail.test.tsx`, the revenue-basis cards/trend case) hit its 20 s timeout under concurrent pytest load; 1,342/1,342 alone | OBSERVATION (test sensitivity to load) | `10-console-codegen.txt` |
| D-O3 | after a top-up credit the receipt task (`create_topup_receipt`) retries `stripe.Invoice.create` through the wrapper and, with no key, logs "Failed to create Stripe receipt invoice … retryable" every retry - expected fail-closed noise under Level 1A | OBSERVATION (logging) | `00-README` failures 5 and 7 |
| D-O4 | `_core`'s `assign_plan` response is still an untyped `additional_properties` dict (the O-8 remainder; `subscribe`'s is a dict too); the `/me/top-up` 202 is now typed | OBSERVATION (DX) | `08-sdk-v5.txt` |
| O-2 | `UBB_INVOICE_PERIOD_DAYS`, `UBB_PLATFORM_FEE_PERCENTAGE`, `UBB_MIN_BALANCE_DEFAULT` read by settings and nothing else; `Tenant.platform_fee_percentage` unread by the fee calculation | OBSERVATION | Stage B |
| O-4 | the subscription lifecycle verbs check charge-readiness before the subscription lookup (422 masks a 404) | OBSERVATION | `06` |
| O-7 | a held undeclared name blocks the tenant period's close (#329); the public remedy is to declare and publish it; `dismiss_as_non_economic` has no public route | OBSERVATION | `04-postpaid` step 12 |
| O-9 | a plain recording into a period pushed in the same month trips `postpaid.snapshot_divergence` (a local-run artefact; production closes the prior month); the related `accumulate_usage: period closed mid-request` line when the current period is closed by hand | OBSERVATION | `00-README` failures 5 |
| O-10 | `reconcile_postpaid_usage` and `reconcile_invoice_payment_status` are global across tenants | OBSERVATION | `04-postpaid` |
| O-11 | Node 24.18.0 used (the brief names 22); no failure attributable | OBSERVATION | `10-console-codegen.txt` |
| O-12 | `vite build` still warns that the main chunk exceeds 500 kB (Stage D: `index-*.js` 1,022.36 kB minified / 274.67 kB gzip; vendor chunks split: react 434 kB, charts 362 kB, router 82 kB) - a code-splitting decision before the console is served | OBSERVATION | `10-console-codegen.txt` |
| - | `GET …/billing-profile` is wallet-adjacent and not behind the wallet door (C5 non-scope observation) | OBSERVATION | PLAN §5.5 |
| - | the referrals real-time flat-fee guard is an unlocked read and a non-CAS write (C5 preflight observation; the reconciler restates the ledger truth) | OBSERVATION | PLAN §5.5 |

Repaired, not inherited: O-1 (C1a), O-5 (C5), O-6 (C1b); O-3 is D2's documentation change.

## 12. What a future owner decision would need to reopen (none required now)

Automatic refund reversal; customer closure; mirror rebinding; a Customer list/search API; an external-id resolver for
credit/debit; any currency but USD; the "all-test" Stripe layout; bounding `ProgramUpdateRequest`'s pre-existing
fields. Each is a ruled non-goal or an explicitly deferred design, not a defect.
