PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# R10-ASH-HANDOFF-2 - index, anchors and the Stage D evidence record

**This folder supersedes `R10-ASH-HANDOFF/` (anchored to `1bf0c0ca`, 2026-11-02) as Ash's entry point.** That folder
stays as it was written, as history. Stage D (the post-C5 re-proof of the billing golden paths) completed on
2026-11-09 NZDT with **zero BILLING BLOCKER and zero PRE-ASH REQUIRED FIX findings** on the anchor below, so this
handoff is **READY**. What Ash inherits is infrastructure, Stripe/environment integration, production SLO/admission
work and accountable human launch decisions - not unexplored billing-product uncertainty (`05-WHAT-ASH-INHERITS.md`).

| File | Read it for |
|---|---|
| **`START-HERE-ASH.md`** | **the short operational transfer note: reading order, the three exact identities, what was proved, what was NOT proved, what Ash does next** |
| `01-WHAT-UBB-IS-NOW.md` | the plain-English picture: the four product domains and the three tenant product flags, the three billing modes, the payment rail, what changed through Stage A-C5, what is NOT in the first launch |
| `02-TECHNICAL-SYSTEM-MAP.md` | the reference by subsystem with `path :: Symbol (line)` citations at the anchor: the money paths, both Stripe receivers, the operator commands, the hourly jobs, the audit actions, SDK 5.0.0 and the Code Builder, the CI/contract gates |
| `03-ASH-VALIDATION-AND-NEXT-STEPS.md` | the safe local recipe, the smallest credible prepaid and postpaid golden paths, the suites, and what cannot be demonstrated locally |
| `04-BILLING-READINESS-MATRIX.md` | the Stage B coverage matrix re-stated at the anchor, and every Stage B finding with its repairing slice, PR and Stage D proof pointer |
| `05-WHAT-ASH-INHERITS.md` | the register: infrastructure, Stripe test credentials / Connect / public receivers, hosting, logging, alerting, SLOs, required checks, the W7 admission act, rail activation, Clerk, the `sdk-v5.0.0` release act (COMPLETED 2026-11-09 - recorded in its §9 as done before handoff), the accepted v1 operational paths, every open ADJACENT/OBSERVATION |

## The three identities (distinct on purpose - do not collapse them)

| Identity | SHA | What it is |
|---|---|---|
| **Behavioural proof anchor (D1)** | `a6738e78e96ab10eabd45dc10fafdc842b7de519` | the Stage C5 squash (#631); every Stage D billing proof and every citation in `01`-`05` was produced on this exact tree |
| **SDK release commit** | `b41b395f59d798cec83289d83d5ec71f83201c7f` | the docs-only Stage D D2 squash (#632), sole parent the D1 anchor; `sdk-v5.0.0` (annotated) dereferences to it; wheel `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948` |
| **Current repository baseline** | `90d008b709a86ff0d63588d8dd6b0a160978230b` | the docs-only SDK release-record squash (#633, `ubb-sdk/CHANGELOG.md`), sole parent the SDK release commit; `origin/main` at the close of the programme and the refreshed W7 starting baseline |

The two successors after the D1 anchor (#632, #633) were documentation/release-record changes only - no code, test,
migration, contract or SDK file - and did not change the billing behaviour that D1 proved. The D1 proof is NOT
relabelled as having run on `90d008b7…`; it ran on `a6738e78…` and stands unchanged on both successors.

### The anchors as first written (provenance)

- **The D1 behavioral proof anchor: `a6738e78e96ab10eabd45dc10fafdc842b7de519`** - `origin/main` at the start of
  Stage D (re-fetched; "Stage C5: the public contract and SDK tell the truth ... (SDK 5.0.0) (#631)", the squash of PR
  #631, sole parent `2c336908`, tree `209d82ce…` identical to the reviewed C5 head `abf5e86f`). Every behavioural
  claim in this folder and every file in `R10-BILLING-STAGE-D-EVIDENCE/` was produced on this exact tree, in the
  worktree `.claude/worktrees/r10-billing-stage-d` (branch `worktree-r10-billing-stage-d`, no D1 commit).
- **The post-D2 `main`: `b41b395f59d798cec83289d83d5ec71f83201c7f` - the documentation-only successor of that proven
  tree, and the repository's current baseline.** D2 was one docs-only PR (#632, reviewed head
  `bcd0899f03833ab3424016b96605b57d023d5fee`: the SDK README's install line and retired product flag, the codegen
  README's stale major and catalogue, the billing and platform glossaries' manual-hold wording), merged under the
  owner's FINAL D2 merge ruling through the temporary R10 merge guard on 2026-11-09 (`mergedAt` 2026-11-09T02:34:50Z).
  Its sole parent is the D1 anchor and its tree is identical to the reviewed head; it changes no code, test,
  migration, contract or SDK file, so the D1 proof stands unchanged on it. Full proof in the **D2 record** below and
  `R10-BILLING-STAGE-D-MERGE.md`. (As first written: "the owner next refreshes the W7 anchor to `b41b395f…` under a
  separate step" - superseded: #633 then moved `main` to `90d008b7…` and the W7 anchor was refreshed to THAT SHA in the
  final transition window, 2026-11-09, below; the W7 STATUS stays `PRE-LAUNCH - NOT FINAL`.)

## When, where, by what

2026-11-09 NZDT, 11:50-13:45 (job `5f69e565`), on the developer's Windows 11 machine: Python 3.13.14 (the developer
venv), Django 6.0.6, stripe-python 15.2.0, pytest 9.0.3; PostgreSQL 16.14 and Redis 7.4.9 in the `ubb-postgres` /
`ubb-redis` containers; Node v24.18.0, pnpm 10.28.2; Docker for the Code Builder execution suite and the codegen shell
image. A fresh disposable database `ubb_stage_d_20261109` (49 migrations), Redis index `/6` for the stack and `/7` for
pytest, a throwaway `SECRET_KEY` and THREE throwaway webhook secrets (billing live, billing test, subscriptions live -
the subscriptions receiver has its own and fails closed without it), `STRIPE_SECRET_KEY` unset in the stack, no
`CLERK_*`, the worktree's own `ubb-sdk` on `PYTHONPATH`. The environment was derived in memory (`probes/env_d.ps1`);
no credential file was written into the worktree. Full detail: `R10-BILLING-STAGE-D-EVIDENCE/00-env.txt`.

## P0 (all nine held)

(a) the launcher heading read AUTHORISED and named D1 then D2 only; (b) `origin/main` = `a6738e78…` exactly;
(c) no open PR against `main`; (d) the PLAN's §9 C5 row filled with that resulting `main`; (e) the manual-hold audit
on the anchor at all five sites (registry, generated constants, published enum, the writing service, the console
label); (f) the Stage B package, the original handoff and the W7 brief unmodified (a 103-file SHA-256 manifest taken
at the start and re-verified at the end - `14-hygiene.txt`); (g) remote tags `api-v1-launch`, `api-v1-cutover`,
`sdk-v4.0.0` present, **no `sdk-v5.0.0`** (none created at that time; created 2026-11-09 in the separate release window - see "The `sdk-v5.0.0` release - COMPLETE" below); (h) no `STRIPE_*`/`CLERK_*` in the shell, the developer
`.env` read for names only; (i) a clean `python -I -s` 3.13 venv in which `import cryptography` failed before the
lock was installed.

## Every command and its result (D1, in order)

| # | What | Result | Evidence (`R10-BILLING-STAGE-D-EVIDENCE/`) |
|---|---|---|---|
| 0 | `manage.py check`; `migrate` ×2; `makemigrations --check --dry-run`; `scripts/export_openapi.py` + `git status -- openapi/`; `openapi/contract_gate.py --baseline origin/main`; `ubb-sdk/codegen/generate_core.py` + `tools.sdk_operations --write` + `git status`; `tools.gates`; `tools.forbidden_terms`; `tools.vocabulary --write`; `pytest apps/platform/tests/test_product_boundaries.py` | 0 issues; **49 applied** (the eleven post-initial app migrations incl. `referrals/0002` applied with no data step), then "No migrations to apply"; "No changes detected"; spec **byte-identical**; **0 breaking changes**; generators **zero diff**; 27/27 gates, 0 owed; 0 retired words; 4 artefacts already up to date; **11 passed** | `00-static.txt` |
| 1 | posture A (`external` + `[metering]`): the Stage B probe unchanged (the regression control) | **34/34** - no wallet anywhere, the handoff golden path intact | `01-posture-A.txt`, `probes/p1_posture_a.py` |
| 2 | posture B (`external` + `[metering, billing]`): the Stage A perimeter AND the F-12 change | **50/50** - the nine wallet-mutating routes 403 `feature_not_enabled` with zero rows (bodies now carry the platform UUID, F-13); the six read-only wallet surfaces **403** (F-12, the ruled NEW behaviour); affordability allowed with `balance_micros`/`available_micros` **null**; plans, the fee period, spend pools, postpaid-config, economics work | `02-posture-B.txt`, `probes/p3_posture_b.py` |
| 3 | prepaid under `off`, the fifteen steps + 9b (manual hold) | **148/148** | `03-prepaid-off.txt`, `probes/p4_prepaid.py` |
| 3 | prepaid under `enforcing` | **153/153** | `03-prepaid-enforcing.txt` |
| 4 | postpaid, the fourteen steps | **100/100** | `04-postpaid.txt`, `probes/p5_postpaid.py` |
| 5 | plans and subscriptions (A-1, A-2 + the reconciler, bind-once, invoice-before-mirror + `reprocess_webhook`, both receivers) | **70/70** (second run; the first run's two FAIL lines were probe-design errors, below) | `06-plans-subscriptions.txt`, `probes/p7_plans_subs.py` |
| 6 | referrals (A-3) | **30/30** (second run; one probe-design error, below) | `07-referrals.txt`, `probes/p8_referrals.py` |
| 7 | the Stripe boundary: Level 1A (the six former raw sites), the AST guard, Level 1B, Level 2 by name | **21/21**; Level 2 **NOT EXECUTED - EXTERNAL DEPENDENCY - STRIPE TEST CREDENTIALS / CONNECT TEST ACCOUNT / PUBLIC TEST WEBHOOK RECEIVER**; `test_live_stripe_ar.py` the only 3 skips | `05-stripe-levels.txt`, `probes/p6_stripe_levels.py` |
| 8 | the SDK v5 journey (Journeys 1 and 2 adapted; `_core`; the /me readback; the Code Builder major) | **65/65** | `08-sdk-v5.txt`, `probes/p10_sdk.py` |
| 9 | convergence jobs from recoverable states | **26/26** | `09-convergence.txt`, `probes/p9_convergence.py` |
| 10 | `pnpm install --frozen-lockfile --prefer-offline`; the console client regenerated under Git Bash + `git status -- apps/ui/src/api/schema.json`; `pnpm ui:api:check`; `pnpm --dir apps/ui typecheck`; `test`; `build`; `pnpm --dir apps/codegen typecheck`, `lint`, `test` (shell image) | install exit 0; regen **zero drift**; `ui:api:check` **exit 1 for an environmental reason** (its npm script is a POSIX inline `API_SPEC_PATH=… bash …`, which cmd.exe cannot run - the Git Bash regen with zero drift is the equivalent proof, as Stage B ran it); typecheck **exit 0**; vitest first run 1 failed (a 20 s test timeout under concurrent pytest load) → **second run alone 139 files / 1,342 passed, exit 0**; build **exit 0** (the TanStack Router plugin rewrote `routeTree.gen.ts` with LF, content identical, restored); codegen typecheck/lint **exit 0**; codegen test **902/902** with `UBB_CODEGEN_SHELL_IMAGE=ubb-codegen-shell`; `git status` empty at the end | `10-console-codegen.txt` |
| 11 | the eight Python trees, foreground, one at a time, partitioned by sorted files (api/v1 ×3, platform+core ×3), union proven against `--collect-only`, stack stopped | **8,192 collected = 8,189 passed + 3 opt-in skips, 0 failed, 0 error; every union OK** | `12-suite-*.collected.txt` / `.partNofM.txt` / `.union.txt`, `12-suite-partition-plan.txt`, `12-suite-union-proof.txt` |
| 12 | the isolated F-16 proof in `clean313` | lock installs `cryptography==50.0.2`, `cffi==2.1.1`, `pycparser==3.12` into the clean venv; `core/tests/test_clerk_auth.py` **15 passed**; CONTROL (cryptography uninstalled there) **7 ERROR + 8 passed**; restored **15 passed** | `13-f16-clean-env-proof.txt` |
| 13 | initial secret hygiene and clean-up; the final pass after the D2 record | see `14-hygiene.txt` | `14-hygiene.txt` |

### The suite total, explained line by line

The launcher expected "the C5 union's **8,186** collected = 8,183 + 3" on this very tree; Stage D collected and ran
**8,192 = 8,189 passed + 3 skipped**. The reconciliation was re-derived mechanically from the two folders' own
`*.collected.txt` files after the consultant's D1 acceptance (`R10-BILLING-STAGE-D-EVIDENCE/22-suite-count-reconciliation.txt`,
script `probes/recount_d.py`). Two distinct facts make up the six:

**(a) Three of the six are a transcription, not tests.** The C5 evidence folder's eight `*.union.txt` files sum to
**8,189 collected = 8,186 passed + 3 skipped** (2,495 + 1,760 + 941 + 242 + 1,346 + 848 + 477 + 80). The launcher's
"8,186 collected = 8,183 + 3" took the C5 *passed* figure as the *collected* figure and subtracted the skips a second
time. C5 and Stage D therefore differ by **three** collected ids, not six.

**(b) The other three are one test class refined between the C5 local run and the C5 commit.** Per tree, every
collected id is identical between the two folders (36 parametrize ids differ only in how a backslash inside the id was
rendered, `[12\n]` vs `[12/n]`, zero net) **except** `apps/referrals/tests/test_endpoints.py::TheUpdateRefusesAFigureOfTheWrongUnitTest`
(the A-3 final-review repair; the class does not exist at the first C5 head `f395c16f`). Three ids are in the C5
collection and not in Stage D's:
`test_a_share_becomes_a_flat_fee_and_the_old_share_is_cleared`,
`test_an_ordinary_same_type_update_of_the_right_figure_succeeds`,
`test_both_figures_are_refused_for_the_resulting_type`;
six are in Stage D's and not in C5's:
`test_a_profit_share_becomes_a_flat_fee_and_the_old_share_is_cleared`,
`test_a_revenue_share_becomes_a_flat_fee_and_the_old_share_is_cleared`,
`test_an_ordinary_same_type_flat_fee_update_succeeds`,
`test_an_ordinary_same_type_share_update_succeeds`,
`test_both_figures_are_refused_whichever_type_results_from_a_flat_fee`,
`test_both_figures_are_refused_whichever_type_results_from_a_share` - net +3 (1,346 → 1,349; the class 9 → 12
cases). Why: the C5 window collected `metering-referrals` at 22:02 on 2026-11-08 (file timestamps 21:59–22:33 for all
eight trees) on the repair's uncommitted working tree; its red proof at 22:07 (`40-repair-redproof.txt`) already lists
the twelve per-type names, so the three generic cases were split into six per-type cases between those two runs (the
`/code-review` refinement the C5 PR body records); the repair was committed as `abf5e86f` at 22:41 with the twelve,
and the anchor's file is byte-identical to `abf5e86f`'s (`git diff --stat abf5e86f a6738e78 -- <file>` empty). The
exact-head CI `test` job on `abf5e86f` and Stage D both ran the committed twelve.

**Nothing was omitted.** No file or suite present in either collection is absent from the other; the only differing
ids are the nine above, all inside one class of one file, and every one of them passed where it was collected.

## Failures and uncertainties (nothing hidden)

1. **Three FAIL lines in first runs were probe-design errors, fixed and re-run; the product behaviour was correct
   both times.** (i) `06-plans-subscriptions`, A-2: my log capture listened on the module logger while
   `apps/subscriptions/orchestration/seats.py` logs `seat.qty_push_failed` on the product logger `ubb.billing` (the
   line IS in the console output of the first run); (ii) `06`, A-2 convergence: I compared the Stripe idempotency key
   to the bare change id, while `set_seats` keys the call `seat-qty-{si}-{change id}` with the deterministic
   `reconcile-{si}-{episode}-{count}` embedded - the key was exactly that; (iii) `07-referrals`, the two-period flat
   fee: the daily task reconciles the current month only, so a prior-month backfill never got a second ledger row -
   the second run reconciles the prior period by hand (`reconcile_all_referrals(tenant, prior_start, prior_end)`) and
   the fee is paid once across two rows. The re-run files replaced the first-run files; the first runs' summaries were
   68/70 and 29/30.
2. **`pnpm ui:api:check` exits 1 on this Windows machine** because `apps/ui`'s `api:sync` script is
   `API_SPEC_PATH=../../openapi/v1.json bash scripts/generate-api.sh regen` - a POSIX inline assignment cmd.exe
   cannot parse ("'API_SPEC_PATH' is not recognized"). Stage B hit the same wall and ran the Git Bash equivalent; so
   did Stage D: `bash -lc 'API_SPEC_PATH=../../openapi/v1.json bash scripts/generate-api.sh regen'` in `apps/ui`,
   then `git status -- apps/ui/src/api/schema.json` → EMPTY (zero drift; the gitignored client was generated). CI runs
   it on Ubuntu. Environment, not product (OBSERVATION, carried in `05`).
3. **The console vitest failed once, then passed alone.** The first run (started 12:53, while the api/v1 pytest
   partitions were running) timed out one test after 20 s
   (`customer-detail.test.tsx` › "states … on the cards and the other basis on the trend"); 1,341 of 1,342 passed. Run
   again alone at 13:36 with nothing else on the machine: 139 files, **1,342 passed**, exit 0. Both runs are in
   `10-console-codegen.txt`. A load-sensitive timeout, not a product defect (OBSERVATION).
4. **The suite total differs from the expected 8,186** - explained above; the per-id diff names every differing id.
5. **Worker log lines while the stack ran** (none is a defect; all recorded in `00-env.txt`/`14-hygiene.txt`): the
   hourly `reconcile_topups_with_stripe` fired at 12:20:00 while a probe tenant held a placeholder connected account
   and was refused BEFORE transport by the wrapper ("Reconcile: PI list failed" - F-2 repaired; no traffic left the
   machine); the top-up receipt task retried at 12:30:00 for the in-process checkout credit of 03-prepaid step 13 and
   failed closed the same way ("Failed to create Stripe receipt invoice - no local record created, retryable"); at
   12:29:47 `accumulate_usage` logged "period closed mid-request / retry also updated zero" once, while 04-postpaid
   step 12 closed the current month's `TenantBillingPeriod` by hand as recordings continued - the local-run artefact
   Stage B recorded as O-9 (production closes the prior month).
6. **Not executed (external dependencies, named):** Level 2 - no `STRIPE_TEST_SECRET_KEY`,
   `STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET`, `STRIPE_CONNECT_TEST_CLIENT_ID`, `STRIPE_TEST_CONNECTED_ACCOUNT` in the
   approved local mechanism or the shell, and no public test receiver (R-1); real-browser console `api` mode - no
   Clerk dev environment exists (`VITE_CLERK_PUBLISHABLE_KEY`, `CLERK_JWKS_URL`/`CLERK_JWT_PUBLIC_KEY`): **F-16 is
   repaired, so this gap is the Clerk environment alone, not missing crypto support**; Level 3 / rail activation (R-2);
   the all-test Stripe layout question (R-3).
7. **The receipt task reached the transport block in the probe process.** After the in-process checkout credit
   (03-prepaid step 13) the `_dispatch_receipt` callback ran immediately and `create_topup_receipt` tried
   `stripe.Invoice.create` through the wrapper with the sentinel in process; the repository's transport block raised
   as designed ("STRIPE TRANSPORT REACHED - blocked"), the receipt was not created (logged retryable) and nothing left
   the machine. Expected under Level 1B; the receipt is not part of any ruled proof.
8. **The in-process checks** (the blank-secret receivers of 03 step 12, the A-1 route failures and the seat push of
   06, the `reprocess_webhook` recovery) ran through the real views/commands in the probe process (Django test
   `Client`, `call_command`) because a running stack's secret cannot be blanked and its key cannot be set without
   transport risk; each is labelled "[in process]" on its evidence line and cross-referenced to its TEST VERIFIED
   suite.
9. **One in-process proof is a fixture, not a client act**, labelled so: the item-43 hand-over (04 step 9) and the
   two-invoice rule use ORM-created pushed usage-invoice rows (the ruling's own test shape); the payment_failed
   backstop proof (09 §7) sets two customers' status/reason by queryset. Every other suspension/recovery was driven
   through the real handlers and routes.

## Findings by classification (the Stage B closed set, applied literally)

- **BILLING BLOCKER: 0.** - **PRE-ASH REQUIRED FIX: 0.** Every F-/A- finding of Stage B is proven repaired on the
  anchor (`04-BILLING-READINESS-MATRIX.md`); no new one appeared.
- **RAIL-ACTIVATION DEPENDENCY: 3** (R-1, R-2, R-3 - unchanged; `05`).
- **ADJACENT PRODUCT FINDING: 0 new.** A-1, A-2, A-3 repaired (C4, C5).
- **OBSERVATION: 4 new** (D-O1 `ui:api:check` not runnable from cmd.exe; D-O2 the load-sensitive 20 s vitest timeout;
  D-O3 the receipt task's immediate retry noise under Level 1A/1B; D-O4 the `_core` response of `assign_plan`
  remains an untyped dict - the O-8 remainder) **and the Stage B observations still open** (O-2, O-4, O-7, O-8, O-9,
  O-10, O-11, O-12; O-3 is D2's docs change) - all in `05-WHAT-ASH-INHERITS.md`.

## Secrets statement

The tenant API keys and widget secrets minted by the probes lived only in the job's temporary directory
(`creds.json`); the Django `SECRET_KEY` and the three throwaway webhook secrets were derived from a seed file there;
the database URL carried the local container's trivial password. All were deleted in `14-hygiene`. No credential was
asked for, searched for or printed; the only secret-bearing file read was the developer `ubb-platform/.env`, for names
only. Every evidence line passed through the harness redactor (every minted key and widget secret, the three throwaway
secrets, the `SECRET_KEY`, the sentinel literal, the password in its URL form); the package - every file of
`R10-BILLING-STAGE-D-EVIDENCE/` and of this folder - was grepped for every one of those values before this folder was
finished (initial pass) and again after the D2 record below (final pass): **no value appears anywhere** (`14-hygiene.txt`).
Pytest's `-rA` output in the suite files carries API keys and widget tokens the tests minted in the disposable test
database (dropped after every run) - documented non-secrets of the same class Stage B recorded.

## Clean-up and what was retained

Dropped: the database `ubb_stage_d_20261109` (and pytest's `test_ubb_stage_d_20261109`); Redis `/6` and `/7` flushed;
the job tmp credentials and seed deleted; the stack processes stopped. Restored: `apps/ui/src/api/schema.json` and
`apps/ui/src/app/routeTree.gen.ts` after the console regen/build (`git checkout --`); `git status --porcelain` empty
in the worktree at the end of D1 (the CLEAN-WORKTREE BOUNDARY of D2). Retained on purpose: the worktree at the anchor
(D1 committed nothing; D2's docs commit is on it), `node_modules`, the gitignored console client and `apps/ui/dist/`,
the pre-existing `ubb-codegen-shell` image, the clean `clean313` venv in the job tmp (deleted with the job), and the
two packages.

## D2 record (evidence-only finalisation, FINAL ruling 5; no repository change)

- **D2 PR: #632** - https://github.com/ashcochrane/ubb/pull/632 - "Stage D docs: the SDK README, the codegen README and
  the glossaries say what main does"; branch `worktree-r10-billing-stage-d` → `main`.
- **D2 head SHA: `bcd0899f03833ab3424016b96605b57d023d5fee`** (one commit on top of the anchor `a6738e78…`).
- **State (as first recorded): DRAFT / OPEN - not merged.** Its merge was not authorised by Stage D's launcher; it
  became the owner's separate act through the temporary R10 merge guard - see **D2 MERGED** below for the outcome.
- **It changes documentation only and does not alter the D1 behavioral anchor:** `git diff --name-only a6738e78…..bcd0899f`
  = `apps/codegen/README.md`, `ubb-platform/apps/billing/CONTEXT.md`, `ubb-platform/apps/platform/CONTEXT.md`,
  `ubb-sdk/README.md` (43 insertions, 6 deletions; both docs-only proofs verbatim in `R10-BILLING-STAGE-D-PR-BODY.md`;
  verification in `R10-BILLING-STAGE-D-EVIDENCE/20-d2-verification.txt`). Every proof in this folder stands on
  `a6738e78…`; #632 has since merged (below), so the resulting `main` `b41b395f…` is the documentation-only successor
  of that proven tree; the owner refreshes W7's anchor to it [since DONE, to the later `90d008b7…` - final transition record below], and `sdk-v5.0.0` may then be tagged on it [DONE] under a
  separate ruling.
- The final secret-hygiene pass over this folder and the evidence package ran after this record was written
  (`R10-BILLING-STAGE-D-EVIDENCE/14-hygiene.txt`, "final").

### Post-D1-acceptance update (consultant's ruling, 2026-11-09; evidence-only, no repository change)

- **D1 substantively ACCEPTED** by the owner/consultant; two evidence-quality closures made in this folder only:
  `01-WHAT-UBB-IS-NOW.md` now distinguishes the four product *domains* from the three tenant product flags
  (`metering`, `billing`, `referrals`; no `subscriptions` flag) and states truthfully what the first launch excludes;
  the suite-count section above was re-derived mechanically (`22-suite-count-reconciliation.txt`, `probes/recount_d.py`).
- **PR #632 marked Ready for review** solely so the guard could evaluate it; head unchanged
  (`bcd0899f03833ab3424016b96605b57d023d5fee`); state **OPEN, READY, NOT MERGED**. Pre-guard checks 1-10 all held
  (`23-pre-guard-checks.txt`): origin/main still `a6738e78…`, base `main`, exactly four `.md` paths, worktree clean,
  MERGEABLE/CLEAN, every exact-head CI job success on both workflow runs, no `sdk-v5.0.0`.
- **The exact D2 patch** is `21-d2-patch.diff` (6,513 bytes, 108 lines,
  SHA-256 `6FC4B0BEAEDDEF19EA15BC45D8E3BDEEC3149124B1A83AD393985B7E03EF351B`; reverse-applies on the head, exit 0;
  details `21-d2-patch.txt`).
- **`python R10-merge-guard.py 632 --check` ran exactly once: exit 0** - "All 5 required checks succeeded for
  bcd0899f03833ab3424016b96605b57d023d5fee. --check: not merging." (`30-guard-check.txt`). Merge mode was not run;
  nothing merged; no tag, no wheel; W7 untouched. Next is the owner's separate explicit D2 merge ruling.
- Hygiene re-run after each of these edits (`14-hygiene.txt`, "post-closure" and "post-guard"): no secret value, every
  header present.

### D2 MERGED - Stage D COMPLETE (the owner's FINAL D2 merge ruling, 2026-11-09; evidence-only record)

| Item | Value |
|---|---|
| D1 behavioral anchor | `a6738e78e96ab10eabd45dc10fafdc842b7de519` |
| D2 PR | #632 |
| Reviewed D2 head | `bcd0899f03833ab3424016b96605b57d023d5fee` |
| Pre-merge identity check | all items held: `origin/main` = the anchor, head as authorised, base `main`, OPEN/Ready, MERGEABLE/CLEAN, twelve exact-head check runs success, exactly the four `.md` paths, no `sdk-v5.0.0` (`R10-BILLING-STAGE-D-EVIDENCE/40-d2-merge-identity-check.txt`) |
| Guard `--check` | exit 0, "All 5 required checks succeeded … --check: not merging." (`30-guard-check.txt`) |
| Guarded merge | `python R10-merge-guard.py 632`, merge mode, run exactly once, exit 0: "MERGED #632 (squash) at head bcd0899f03833ab3424016b96605b57d023d5fee." (`41-d2-guard-merge.txt`); guard script SHA-256 `BE2BEFAD…5F80B`, unchanged |
| **Resulting post-D2 `main`** | **`b41b395f59d798cec83289d83d5ec71f83201c7f`** ("Stage D docs: the SDK README, the codegen README and the glossaries say what main does (#632)") |
| `mergedAt` | 2026-11-09T02:34:50Z (15:34:50 +1300) |
| Parents / intervening commits | exactly one parent, `a6738e78…`; `git log --oneline a6738e78..origin/main` = the one squash commit (`42-d2-post-merge-proof.txt`) |
| Reviewed-head tree = resulting-main tree | `d8223f8e28b70f2e2a537f89699b2efefccbd4b8` = `d8223f8e28b70f2e2a537f89699b2efefccbd4b8` |
| `git diff --stat bcd0899f… origin/main` | empty |
| `git diff --name-only a6738e78…..origin/main` | `apps/codegen/README.md`, `ubb-platform/apps/billing/CONTEXT.md`, `ubb-platform/apps/platform/CONTEXT.md`, `ubb-sdk/README.md` - nothing else (4 files, +43/-6; patch SHA-256 identical to `21-d2-patch.diff`) |
| Documentation-only | yes: no code, test, migration, contract, generated artefact, SDK or console file |
| Suite-count reconciliation | recorded above and in `22-suite-count-reconciliation.txt`: the C5 prose misstated collected vs passed by three; the other net +3 is three generic referral update tests split into six per-type tests before the committed final C5 repair head; no intended suite or file omitted; exact-head CI and Stage D exercised the committed twelve-case class; the raw C5 evidence is left as recorded |
| `sdk-v5.0.0` | **NOT CREATED at the D2 merge**; no wheel built then (remote tags: `api-v1-launch`, `api-v1-cutover`, `sdk-v4.0.0`). **Since created and built - 2026-11-09, the separate release window; see "The `sdk-v5.0.0` release - COMPLETE" below** |
| W7 | **NOT REFRESHED**; `R10-W7-DELIVERY-PROMPT.md` untouched; STATUS `PRE-LAUNCH - NOT FINAL` |
| Final hygiene | `14-hygiene.txt`, "post-merge" pass over both packages after this record |

**Stage D is COMPLETE. This folder is the authoritative engineering handoff package for Ash.** `R10-ASH-HANDOFF/`
remains immutable and historical. The next owner sequence, each step separately authorised: (1) the `sdk-v5.0.0`
tag and reproducible wheel on `b41b395f…` - **DONE 2026-11-09**; (2) verify that release - **DONE 2026-11-09** (both
below); (3) refresh W7's anchor - **DONE 2026-11-09** in the final transition window, to the then-current `main` `90d008b7…`
(not `b41b395f…`, which #633 had by then succeeded; pointer only, STATUS unchanged); (4) hand this folder to Ash -
**DONE 2026-11-09** (`START-HERE-ASH.md` + the owner's transfer message). Durable records: `R10-BILLING-STAGE-D-MERGE.md`,
`R10-BILLING-READINESS-FINAL-TRANSITION.md`.

### The `sdk-v5.0.0` release - COMPLETE (the owner's separate release ruling, 2026-11-09; evidence-only record)

| Item | Value |
|---|---|
| Authoritative `main` (unchanged before, during and after) | `b41b395f59d798cec83289d83d5ec71f83201c7f` |
| Tag | `sdk-v5.0.0`, **annotated** (`git cat-file -t` = `tag`), object `fbf765b7efc19c2f3b08f2313ae6e72923e4b340`, dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`; message "ubb-sdk 5.0.0, the one deliberate major after the cutover (R10 billing readiness Stage C5, #631; ADR-0026)" |
| Remote proof | pushed as the one tag ref only (`refs/tags/sdk-v5.0.0`); `git ls-remote --tags origin` shows `sdk-v5.0.0` = `fbf765b7…`, `sdk-v5.0.0^{}` = `b41b395f…`; `sdk-v4.0.0`, `api-v1-cutover`, `api-v1-launch` unmoved |
| Build | the tag's own `ubb-sdk/release/build_wheel.py` (SHA-256 `f6bbb0d3…`) from a clean detached worktree at `b41b395f…`, Python 3.13.14, the hashed lock `7bd4b746…` and no installer in the build environment, `SOURCE_DATE_EPOCH` 1794191690; two builds, one SHA-256; exit 0 |
| **Wheel** | **`ubb_sdk-5.0.0-py3-none-any.whl`**, SHA-256 **`56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`** |
| Release manifest | `R10-SDK-V5-RELEASE/sdk-v5.0.0.release.json` |
| Verification | wheel contents = the tag's `ubb-sdk/ubb/` blobs 650/650; fresh clean venv install from the wheel file, `ubb.__version__` and package metadata `5.0.0`, `__spec_revision__` `1bf1af23…`; `tests/test_release.py` 23 passed and the whole SDK suite 477 passed (63 subtests) against the INSTALLED wheel; `tools/verify_sdk_v5_release.py` RELEASE EVIDENCE VALID |
| Handed over as | a release artefact in **`R10-SDK-V5-RELEASE/`** (project folder; never committed) |
| **Not published** | nothing was uploaded to PyPI or any index |
| Repository | no file changed, no PR; `main` = `b41b395f59d798cec83289d83d5ec71f83201c7f` throughout |
| W7 | untouched; STATUS `PRE-LAUNCH - NOT FINAL`; the anchor refresh to `b41b395f…` stays the owner's next separately authorised step |
| D1 behavioral anchor | `a6738e78e96ab10eabd45dc10fafdc842b7de519` - unchanged; nothing in this record alters the Stage D proofs |

Durable record: `R10-SDK-V5-RELEASE/00-README.md` and its `evidence/`.

**Post-release recording PR (evidence note, 2026-11-09; the release itself is complete and unchanged):** the owner
accepted the release and ruled one documentation-truth item - record the released wheel's identity in
`ubb-sdk/CHANGELOG.md` in the 4.0.0 convention. Draft PR **#633** "SDK v5 release record: pin the released wheel
SHA-256", head `1c347bd6efd147870fa340bc9c44377d09bbce7e` (one file, `ubb-sdk/CHANGELOG.md`; parent `b41b395f…`),
state **MERGED** (the owner's FINAL merge ruling, 2026-11-09): exact-head CI green on both workflow runs, `R10-merge-guard.py 633 --check` exit 0, then `python R10-merge-guard.py 633` (merge mode, once) exit 0 → **`main` = `90d008b709a86ff0d63588d8dd6b0a160978230b`**, `mergedAt` 2026-11-09T03:55:58Z, sole parent `b41b395f…`, reviewed-head tree = resulting-main tree `e453d89e…`, `git diff --stat 1c347bd6 origin/main` empty, exactly one path changed. The SDK release identity is unchanged by it: `sdk-v5.0.0` object `fbf765b7…` still dereferences to `b41b395f…` (the tag was NOT moved to the docs commit), the wheel SHA-256 is still `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`, no wheel rebuilt, nothing published. **The SDK release and its repository release record are now BOTH complete before the Ash handoff.** `90d008b7…` is the documentation-only successor of `b41b395f…`; every behavioural proof in this folder still stands on the D1 anchor `a6738e78…`. Evidence: `R10-SDK-V5-RELEASE/evidence/08-…`, `09-…`, `10-guard-merge.txt`. W7's anchor refresh (to `90d008b7…`) and the Ash transfer were then completed in the final transition window (the closing record below).


## FINAL TRANSITION WINDOW - 2026-11-09 - programme closure (evidence-only record)

P0 re-established before any edit: `origin/main` = `90d008b709a86ff0d63588d8dd6b0a160978230b` exactly; no open PR against `main`; no
tracked file modified; remote `sdk-v5.0.0` still an annotated tag (object `fbf765b7…`) dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`;
retained wheel SHA-256 still `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`; PR #633 MERGED; this folder already recorded Stage D
COMPLETE, the SDK release COMPLETE, the release record COMPLETE, BILLING BLOCKER 0, PRE-ASH REQUIRED FIX 0; the W7 prompt
read `PRE-LAUNCH — NOT FINAL`.

Done in this window (project-folder evidence/prompt files only; no repository file, PR, tag, wheel, deployment, credential,
rail or tenant was touched):

1. `R10-W7-DELIVERY-PROMPT.md`: the starting-baseline pointer moved from `a674e9d0` to `90d008b709a86ff0d63588d8dd6b0a160978230b` (the
   STATUS paragraph's refresh sentence and P0(g)); a factual note under §0.5 step 13 records that `sdk-v5.0.0` exists and
   that the client-SDK-major question is an owner policy matter left unchanged [since RULED v5 - see the FINAL ruling
   paragraph below; the note was replaced by the ruled step-13 instruction]. STATUS remained `PRE-LAUNCH — NOT FINAL`.
   W7 was not executed.
2. This folder: the three-identities table above; `03` and `05` updated so no sentence still says the W7 refresh or the Ash
   transfer is pending; `05` gained §0 (completed items that are NOT Ash's work); `START-HERE-ASH.md` created.
3. Hygiene: secret/header pass over `R10-ASH-HANDOFF-2/` and `R10-SDK-V5-RELEASE/`; `R10-ASH-HANDOFF/` (4 files) and
   `R10-BILLING-READINESS/` (98 files) verified byte-identical to their pre-window SHA-256 manifests. Results in
   `R10-BILLING-READINESS-FINAL-TRANSITION.md`.

FINAL owner/consultant ruling (2026-11-09, after the review of this window): the first client receives `sdk-v5.0.0` if it
integrates through the Python SDK (wheel `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256
`56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`, `R10-SDK-V5-RELEASE/`); W7's operative SDK v4 references were updated
accordingly and the step-13 policy note removed; the historical R2 quotation is preserved and marked superseded for this
question. No unresolved internal owner decision remains in this handoff.

**Final programme disposition: `R10 BILLING READINESS: INTERNAL PROGRAMME COMPLETE — HANDED FORWARD TO ASH`.**
**`FINAL OWNER POLICY CLOSURE: first-client Python SDK = sdk-v5.0.0.`**
Internal billing repair (Stage A, C1a-C5), verification and handoff (Stage B, Stage D, this folder) and the SDK v5 release
(tag, wheel, verification, repository record) are complete. The remaining work is the W7/external operational lane in
`05-WHAT-ASH-INHERITS.md`. This disposition does NOT mean production-ready, W7 passed, a first customer admitted or a
payment rail activated - none of those has happened.

## The historical handoff

`R10-ASH-HANDOFF/` (anchor `1bf0c0ca772410fa5aa721f733736f5f83e66760`, 2026-11-02) is **historical**: its one
`HANDOFF DISCREPANCY` (three residual "not postpaid?" wallet checks) was resolved by Stage A (#625), and every later
finding of Stage B (`R10-BILLING-READINESS/findings.md`) is repaired on this anchor. Its plain-English overview and
system map remain accurate for the kernel and metering; this folder's `01` and `02` restate them at the new anchor
with the billing, subscriptions and referrals changes of Stage A-C5 folded in.
