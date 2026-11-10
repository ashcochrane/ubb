# R10-W7 — Delivery close-out: deploy, measure, audit, admit

> **STATUS: PRE-LAUNCH — NOT FINAL.** Refreshed at `main` = `90d008b7` (2026-11-09, the FINAL TRANSITION WINDOW of the
> pre-Ash billing-readiness programme — a baseline-pointer refresh only; W7 was NOT executed. The W7 starting repository
> baseline is now `90d008b709a86ff0d63588d8dd6b0a160978230b`, the squash of the docs-only SDK release-record PR #633; its sole
> parent is `b41b395f59d798cec83289d83d5ec71f83201c7f` (the squash of the docs-only Stage D D2 PR #632), whose sole parent is
> `a6738e78e96ab10eabd45dc10fafdc842b7de519` (the squash of Stage C5 PR #631) — the Stage D behavioural proof anchor, on which
> every billing golden path was re-proven with zero BILLING BLOCKER and zero PRE-ASH REQUIRED FIX (`R10-ASH-HANDOFF-2/`).
> The two successors after that anchor are documentation/release-record changes only and changed no billing behaviour.
> Also since the previous refresh: billing-readiness Stage C1a–C5 (#626–#631) merged through the temporary R10 merge
> guard, and `sdk-v5.0.0` was released — an annotated tag dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`, wheel
> `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`,
> `R10-SDK-V5-RELEASE/`, not published to PyPI; **FINAL owner/consultant ruling, 2026-11-09: the first client receives
> `sdk-v5.0.0` if it integrates through the Python SDK (§0.5 step 13; supersedes R2's SDK v4 default)**. None of this is W7 admission
> evidence. The temporary R10/W7 merge guard was a compensating control for those merges, not branch protection; native
> required-check enforcement on `main` remains the accepted temporary governance limitation (§0.0) until the repository
> owner applies the ruleset. W7 has NOT been executed: no deployment, hosting, SLO measurement, production credential,
> rail activation or real-client admission has occurred because this anchor moved; `api-v1-cutover^{}` still `c2eb35ff`;
> the seven launch inputs still blank. The internal billing-readiness programme is closed and handed forward to Ash
> (`R10-ASH-HANDOFF-2/START-HERE-ASH.md`). Before that at `main` = `a674e9d0` (2026-11-02, later: the pre-Ash billing
> readiness Stage A PR #625 — the wallet-subject mutation perimeter — merged through the guard at reviewed head
> `f8539dd7` under the Stage-A-only authorisation, squash `a674e9d0a2430601a4e5350d55c59e6221daa147`, record
> `R10-BILLING-STAGE-A-MERGE.md`; it is not W7 admission evidence; `api-v1-cutover^{}` still `c2eb35ff`; the seven
> launch inputs still blank). Before that at `main` = `1bf0c0ca` (2026-11-02: the ONE pre-FINAL readiness-fix
> PR #624 — F1+F2, F3, F5, F6 — merged through the guard at head `6e708b29`; §0.5 step 0 is **DONE PRE-FINAL**, F8 is done,
> and the real W7 now starts at step 1, the deployment-files PR; `api-v1-cutover^{}` still `c2eb35ff`). Earlier refreshed
> at `main` = `cf4f5189` (2026-10-29) with the W7 governance exception
> (§0.0), the five owner/consultant rulings of 2026-10-29 (§0.1–§0.5) and their three final refinements (SLO 2's
> client-receipt boundary and the pre-admission tenant's hygiene in §0.2–§0.3; SLO 3's verbatim profile in §3; the
> audit as an admission recommendation and the post-admission record on #540 in §0.4–§0.5) folded in as BINDING
> amendments — then the last three planning corrections (2026-10-30): the 15-step sequence in which the signed-audit
> PR no longer deletes the dated note and a docs-only admission-record PR does so only after admission (§0.5); one
> authoritative external-mode SLO 3 execution profile beside the verbatim source (§0.2, §3); and the #540 comment as
> the only completion evidence (§0.5 step 15, END) — and finally four execution rulings (2026-10-30): a second live
> re-verification as the first act of step 11; three PLANNED PRs plus an admission-blocker fix PR only under §0.4's
> rules (the audit wins over the PR count); LAUNCH INPUT 7, the alert recipient; and SLO 1's fault-window criteria
> fixed before the run (§0.2). Then, 2026-10-30, **the preparation-pass rulings (§0.6)**: the ONE allowed preparation
> pass RAN (`R10-W7-PREP/`, findings F1–F10) and its findings were accepted as planning evidence and ruled — five
> product defects (F1, F2, F3, F5, F6) are repaired in ONE W7 readiness-fix PR, the new **step 0**, before the
> deployment-files PR and before any release SHA is recorded; SLO 2's customer-wide legs are carried forward (F4);
> SLO 1 runs first on the real host (F7); the release-evidence tool's re-record guard (F8) is applied and re-validated;
> the runbook facts (F9, F10) bind. §0.6 supersedes any older wording that conflicts with it. **The plan is complete.
> The only remaining blocker is the SEVEN LAUNCH INPUTS below**, then one final factual review. **Do not launch W7
> until this line reads FINAL.** The product fixes are the first work of the fresh W7 session after FINAL — never
> earlier. There is no second preparation pass; the inputs are never placeholders.
> W6 is accepted complete (#622 → `c2eb35ff`, #623 → `cf4f5189`; #190 and #194 closed; register 23/23).

**The final factual review — not another architecture or design review.** Once the delivery owner supplies all seven
values, they are inserted exactly as supplied, and the review checks only that: the values are real and internally
coherent; the hosting service can support the ruled one-image, three-role, deploy-by-digest shape; the region and
account facts are unambiguous; the named human roles are accurate; the client is genuinely the first `external`
tenant; and the alert destination is usable. It also **binds §0.5 step 12 to the client integration path that
actually applies** (from the preparation pass's `client-golden-path.md`, verdict `CLIENT GOLDEN PATH READY`,
accepted 2026-10-30; SDK major RULED v5 on 2026-11-09): **P2** if the client integrates through SDK v5; otherwise **P1** if it integrates directly with
the API; **P3** where a real Task lifecycle is representative; webhook push is supplementary, never the sole proof.
Step 12 must prove both **client → UBB** (a real controlled action reaches and is processed by UBB) and **UBB →
client** (the resulting state is observable through a supported client-facing surface) — the minimal chain is
*client action → authoritative UBB processing/persistence → supported client-visible readback → the #561
usage-summary proof*; a health check, a container's running status or a database row alone is not proof that the
product works for the client, and no traditional UI is built merely to prove admission. If those facts hold, STATUS
becomes FINAL and W7 launches in a fresh session with only the LAUNCHER block.

## W7 PREPARATION PASS — allowed while PRE-LAUNCH (owner/consultant ruling, 2026-10-30; APPROVED to run, with the clarifications below) — RAN 2026-10-30, DONE

> **Ran 2026-10-30** against `cf4f5189` (P0 held). Output: `R10-W7-PREP/` — `00-README.md` (index and summary),
> `findings.md` (F1–F10 with evidence), `client-golden-path.md` (verdict `CLIENT GOLDEN PATH READY`). Its findings were
> accepted as planning evidence and are ruled in **§0.6**. The section below is kept as the record of what the pass
> was allowed to do; it is not run again, and nothing it produced counts toward §0's controls.

The seven LAUNCH INPUTS are operational facts, never template variables: **no placeholder is ever written into them,
and STATUS stays PRE-LAUNCH — NOT FINAL** until they are real. While they are being obtained, ONE preparation pass is
allowed. It performs **no production deployment and no admission act**, and **every artifact it produces is labelled
`PREPARATION — NOT ADMISSION EVIDENCE`** (in its title and first line). Nothing it produces counts toward §0's controls:
the real W7 re-derives or re-verifies anything it reuses.

**It may:**
- inspect and validate the generic container/image build — drafting the container definition and building it locally
  with the revision label; **no PR and no merge** (the deployment-files PR is real W7 step 1, after FINAL);
- **demonstrate locally / on non-production infrastructure that the ONE draft image supports all four operational
  invocations** W7 will need: the **web** process, the **Celery worker**, **Celery beat**, and the **one-off database
  migration** command — smoked, where practical, against local **PostgreSQL 16 and Redis 7** (the repository's
  `docker-compose.yml` already runs `postgres:16` and `redis:7`; use a dedicated preparation database, never the
  developer `ubb` database or a test database another session uses). Preparation evidence only — never an
  authoritative production result;
- build the **environment/configuration inventory by name only — never a value**, classifying every name as
  **required or optional**, **ordinary configuration or secret**, and **which runtime role(s) consume it** (web,
  worker, beat, migration);
- verify the release-evidence tooling (`R10-W7-RELEASE-EVIDENCE.py`) end to end against a scratch directory and
  synthetic or locally built digests;
- prepare and validate the SLO harness and the controlled external webhook receiver **locally or on non-production
  infrastructure** (SLO 2's one-clock receipt measurement, SLO 1's fault-window criteria, SLO 3's external-mode profile);
- inspect and document the canonical application/admin path for creating the first tenant (never raw SQL);
- inspect current code to identify the applicable cap-crossing and non-top-up-clear paths for the external-mode SLO 3
  choreography (§3), with how many of each the harness can drive;
- establish what the pre-admission tenant's separation and cleanup options actually are, from code (`Tenant.is_sandbox`
  is not assumed to exclude anything — §0.3);
- produce a provider-facing infrastructure checklist: web, worker and beat from one image; Postgres 16; Redis 7;
  deployment by image digest; the one-off migration; the log drain; the alert destination; and the required
  configuration (by name);
- **map the real-client "golden path"** (owner/consultant addition, 2026-10-30 — bounded; not a new architecture
  decision): determine **from current code** exactly how the real W7 can later prove the first client is actually
  using UBB successfully. Do not assume a traditional UI. Identify the client-facing surfaces that **actually exist
  today** — where applicable: API endpoints; `ubb-sdk` calls; the Code Builder's generated integration; webhook
  delivery; console surfaces; the #561 end-customer usage summary/widget; any supported read/report endpoint that lets
  the client observe the result. **Never invent a surface that is not present.** Write
  `R10-W7-PREP/client-golden-path.md` (labelled `PREPARATION — NOT ADMISSION EVIDENCE`), recording in plain English,
  **for each viable path**:
  1. **how the client sends something into UBB** — the exact API/SDK/code-generated entry point, and the
     authentication mechanism by NAME/type only, never a credential value;
  2. **what controlled action we can perform** — preferably one small representative usage event or Task action; no
     payment rail;
  3. **what UBB should persist/process** — the authoritative internal/economic result that proves the write was real;
  4. **what the client can observe** — the exact API/SDK readback, UI, widget or webhook surface, and what result
     should appear there;
  5. **what downstream behaviour is relevant** — e.g. pricing/Posting, Task state, a ceiling/stop response, a webhook,
     reporting — only where it actually applies;
  6. **the proposed minimal production admission smoke path** — one write/action; one authoritative processing proof;
     one client-visible/readable proof; and the #561 usage-summary proof already required.

  Then state exactly one verdict: **`CLIENT GOLDEN PATH READY`** with the concrete candidate path(s), or **`CLIENT
  GOLDEN PATH BLOCKED`** with the exact missing capability/evidence. If several supported paths exist, list them all and
  identify the smallest credible one — **without choosing which one the actual first client uses** unless current
  evidence already establishes it. **If no faithful client-visible end-to-end path exists, that is a real W7 admission
  blocker: report it (§0.4); do not patch UBB.** A health check, a container's running status or a database row alone is
  never a client-visible proof.

**It must NOT:** choose or invent the hosting provider; provision production infrastructure; use placeholder region or
account facts as if real; build admission evidence against a fake production target; run the authoritative production
SLOs; sign the acceptance audit; create the real client tenant; delete the compatibility note; open or merge any W7 PR;
fill any LAUNCH INPUT; or mark W7 complete or FINAL. Local test data stays local — the harness is never pointed at a
production target.

**Preparation artifacts may be iterated; the product may not.** The pass may correct its own preparation-only
artifacts as it goes — the local draft container definition, the local harness, the webhook receiver, the preparation
documentation — fixing them locally and re-validating. That does **not** authorise fixing UBB itself. **If preparation
discovers a real defect in application behaviour, economic correctness, tenant isolation, admission enforcement, public
API/SDK behaviour, or any other §0.4 blocker: report it, capture the evidence, and do NOT patch the product** — it is
left for the real W7's blocker-fix path (§0.4) after FINAL.

**Where its output goes:** `R10-W7-PREP/` in this project folder (`00-README.md` first, indexing every artifact). Any
draft repository file lives only on a local, unpushed branch (or in that folder). **No PR, no merge, no production
resources, no FINAL status.**

**The end report** returns the indexed `R10-W7-PREP/` findings and a **plain-English summary** with four parts:
1. **what is technically ready**;
2. **what the real W7 must re-derive or re-verify against the chosen real host**;
3. **any actual blocker discovered** (with its evidence) — or "none found";
4. **what still depends specifically on LAUNCH INPUTS 1–3 and 7** (provider/service, region, account holder, alert
   destination);

and, beside them, the **client golden path verdict** (`CLIENT GOLDEN PATH READY` with the candidate path(s) and the
smallest credible one, or `CLIENT GOLDEN PATH BLOCKED` with what is missing).

### PREPARATION LAUNCHER (RAN 2026-10-30 — kept as a record; do not paste it again)

```
Read C:\Users\tom_l\.claude\projects\C--Users-tom-l-git-ubb\R10-W7-DELIVERY-PROMPT.md in full. You are the W7
PREPARATION PASS only - NOT W7. Follow its section "W7 PREPARATION PASS" exactly: its MAY list, its MUST-NOT list,
its labelling and its output folder. The brief is PRE-LAUNCH - NOT FINAL and must stay so.

P0 - STOP if any is false:
  (a) The STATUS line reads PRE-LAUNCH - NOT FINAL (if it reads FINAL, run the real W7 LAUNCHER instead).
  (b) origin/main still has slice_8.landed: true and api-v1-cutover^{} = c2eb35ff.

Must not miss:
  1. No production deployment, no production infrastructure, no admission act, no PR, no merge, no tenant for the
     real client, no audit signature, no compatibility-note deletion, no LAUNCH INPUT filled, no FINAL.
  2. Every artifact titled and opened with: PREPARATION - NOT ADMISSION EVIDENCE. Output to R10-W7-PREP/, indexed
     by 00-README.md.
  3. Show the ONE draft image runs all four invocations - web, Celery worker, Celery beat, the one-off migration -
     against local Postgres 16 and Redis 7 (a dedicated prep database, never `ubb`). Preparation evidence only.
  4. Config inventory by NAME only - never a value: each name required/optional, configuration/secret, and the
     role(s) that consume it (web, worker, beat, migration).
  5. Local or non-production infrastructure only; the SLO harness is never pointed at production; nothing it measures
     is an authoritative SLO result.
  6. Read the code before claiming a path exists (tenant creation, cap crossings, non-top-up clears, is_sandbox).
  7. Fix your own PREPARATION artifacts freely; NEVER patch UBB itself. A real product/sec 0.4 defect is reported
     with its evidence and left for the real W7's blocker-fix path.
  8. One pytest at a time; the worktree conventions in memory/ubb-standing-cautions.md apply.
  9. Map the real-client GOLDEN PATH from current code into R10-W7-PREP/client-golden-path.md: for each surface that
     ACTUALLY exists (API, ubb-sdk, Code Builder output, webhooks, console, the #561 widget, read/report endpoints -
     never an invented one), the six parts in the section (client sends; controlled action, no rail; what UBB
     persists; what the client observes; relevant downstream behaviour; the minimal admission smoke path). Verdict:
     CLIENT GOLDEN PATH READY (candidates + the smallest credible one; do not pick the client's) or BLOCKED (what is
     missing - a real W7 blocker, reported, not patched). A health check or DB row alone is never client proof.
 10. End with the indexed R10-W7-PREP/ findings and a plain-English summary: (1) what is technically ready;
     (2) what the real W7 must re-derive/re-verify on the chosen host; (3) any actual blocker, with evidence;
     (4) what still depends on LAUNCH INPUTS 1-3 and 7; plus the golden path verdict.
```

## LAUNCH INPUTS — the owner fills these; W7 STOPS if any is blank. Never inferred, never invented.

| # | Input | Value |
|---|---|---|
| 1 | **Hosting provider** — the exact provider AND service (e.g. a named container/app service), not a generic "cloud" | ______ |
| 2 | **Region** — the exact deployment region identifier | ______ |
| 3 | **Account holder** — the organisation/person/account under which the production resources live, unambiguous enough for the audit | ______ |
| 4 | **Acceptance-audit signer** — the actual person's full name | ______ |
| 5 | **First real `external` tenant** — the actual client/tenant identity; not a placeholder and not a test tenant | ______ |
| 6 | **Governance-exception decision-maker** — the named human who accepted the W7 exception and the admission risk (§0.0, §0.4). If the same person as 4, write "same as 4" explicitly | ______ |
| 7 | **Alert recipient** — the exact email address, named distribution address, or already-existing accountable alert destination that will receive W7's owner alerts (§0.5 step 4). If the hosting provider routes alerts through a named notification destination rather than a literal email field, name that exact destination plus its accountable recipient | ______ |

## LAUNCHER (paste only this block into a fresh window)

```
Read C:\Users\tom_l\.claude\projects\C--Users-tom-l-git-ubb\R10-W7-DELIVERY-PROMPT.md in full and follow its
FULL BRIEF exactly; sec 0.6 (the preparation-pass rulings of 2026-10-30) binds over any older wording. You are
window W7, the last window of the approved close-out plan: first repair the five ruled readiness defects, then
deploy ONE exact release artifact, measure the applicable SLOs on controlled pre-admission data, run the ADR-0008
acceptance audit, and - only if all of that passes - admit the first real external-mode tenant.

P0 - STOP if any is false:
  (a) The file's STATUS line reads FINAL, and all SEVEN LAUNCH INPUTS hold real values (none inferred).
  (b) GOVERNANCE: run R10-W7-VERIFY-REQUIRED-CHECKS.py. If it prints MAIN NATIVELY REQUIRES THE FOUR CHECKS,
      record that; otherwise proceed ONLY under the W7 governance exception (sec 0.0) and NEVER write that native
      checks are enforced.
  (c) W6 is merged: slice_8.landed is true on origin/main, api-v1-cutover^{} = c2eb35ff, #190 and #194 closed.
  (d) #190's spec part 4 and W6's hand-forward on #190 (comment 6508750367) are read.
  (e) sec 0.6 and R10-W7-PREP/findings.md are read, and R10-W7-RELEASE-EVIDENCE.py carries the F8 re-record
      guard (its record command refuses a SHA whose evidence already names an artifact).
  (f) STEP 0 IS ALREADY ON MAIN: origin/main contains the squash of readiness-fix PR #624 (1bf0c0ca, merged
      2026-11-02 through the guard) - `git merge-base --is-ancestor 1bf0c0ca origin/main` holds, #624 reads MERGED,
      and the readiness evidence (R10-W7-PREP/readiness/) is read. Do NOT implement F1/F2/F3/F5/F6 again. If any
      of that is false, STOP.
  (g) THE EXPECTED BASELINE IS THE FINAL POST-PROGRAMME MAIN: origin/main equals exactly
      90d008b709a86ff0d63588d8dd6b0a160978230b (the squash of the docs-only SDK release-record PR #633, merged
      2026-11-09 through the guard; sole parent b41b395f59d798cec83289d83d5ec71f83201c7f = the docs-only Stage D D2
      squash #632; its sole parent a6738e78e96ab10eabd45dc10fafdc842b7de519 = the Stage C5 squash #631 and the Stage D
      behavioural proof anchor; records R10-BILLING-STAGE-D-MERGE.md and R10-SDK-V5-RELEASE/00-README.md), #625-#633
      read MERGED, and `git merge-base --is-ancestor a674e9d0 origin/main` and `... a6738e78 origin/main` both hold.
      If origin/main has moved past it, STOP and report the SHA (the owner refreshes this line; no further pre-W7
      mover is expected). Stage A-D and the sdk-v5.0.0 release are not admission evidence and authorised nothing here.

Must not miss:
  0. STEP 0 (sec 0.5, sec 0.6) IS DONE PRE-FINAL - verify it per P0(f); never re-implement it. Never record, build
     or deploy a release from a commit that does not contain it.
  1. ONE application image, deployed BY DIGEST as separate web, Celery-worker and Celery-beat roles, on managed
     Postgres 16 and Redis 7; the sec 0.6 F9 runbook facts bind the deployment files and the host.
  2. Release identity (sec 0.1): reviewed SHA + PRs + exact-head CI + OCI revision label + image reference +
     immutable digest + host release id + all three roles on that digest. Never a mutable tag. A rebuild from the
     same commit is a different artifact.
  3. SLOs (sec 0.2, sec 0.6, sec 3): SLO 1 runs FIRST on the real host - before SLO 2, SLO 3 or the audit - at the
     required batch sizes INCLUDING 100 items; any applicable SLO 1 miss STOPS W7 with the authoritative evidence
     (never retargeted, averaged away or called an accepted limitation). Conditions recorded BEFORE each run; raw
     evidence kept for every authoritative attempt; an applicable miss STOPS admission - never averaged, discarded,
     rerun-until-green or re-parameterised. SLO 1's fault windows: criteria recorded BEFORE the run, full raw data
     kept, never chosen after a miss. SLO 2 applies to task.killed and subtask.killed only (plus the separate in-band
     verdict), measured at a controlled external receiver's ACCEPT time on one clock (never an internal/queue/send/
     DB time); customer-wide customer.stopped / customer.stop_cleared and the top-up resume are NOT applicable -
     carried, never driven, never invented, never counted as passes. SLO 3 runs the sec 3 EXTERNAL-MODE EXECUTION
     PROFILE: Task and Subtask ceiling crossings, no customer-wide crossing or clear, the rail-only legs omitted and
     reported "not applicable - carried" (never passes), no invented equivalents, the applicable choreography
     stated from code before the run.
  4. Pre-admission data (sec 0.3): a clearly named non-customer pre-admission tenant, its separation from customer
     data and its post-admission fate proven from code first (is_sandbox is not an exclusion flag); never
     seed_dev_data in production; never the real client before O2.
  5. Audit (sec 0.4): blockers block admission; only the ruled operational limitations are accepted; record the
     named decision-maker and signer; "owner" means the delivery/product decision owner. The signed audit is an
     admission RECOMMENDATION - never "admitted"; the post-admission result record is one #540 comment (step 15).
  6. Sequence (sec 0.5): step 0, then its 15 steps, in order. The real tenant is created only after the signed-audit
     PR (which does NOT delete the dated note) is on main, and step 11 BEGINS with a final live re-verification
     (source SHA, release/target, web/worker/beat digests read from the host; ADMISSION RE-VERIFIED or STOP), then
     the ruled operator path (sec 0.6 F10): an operator-run Django shell using the existing model/service APIs,
     never raw SQL; the first API key by TenantApiKey.create_key; billing_mode external, no payment rail. Step 12
     uses the client's actual integration path (P2 if SDK v5, otherwise P1 direct API; P3 where a real Task
     lifecycle is representative; webhooks supplementary, never the sole proof) plus the #561 proof. Only after
     steps 11-13 succeed does a docs-only admission-record PR delete the note.
  7. Every W7 PR merges ONLY through R10-merge-guard.py (five checks), its body carrying the guard sentence. No
     direct gh pr merge, no direct push.
  8. No production secret value in Git, PR bodies, audit documents or logs - and the #561 widget secret goes to the
     client only through an out-of-band secret channel, never into Git, a PR, the audit, any artifact or #540.
  9. Three PLANNED W7 PRs remain: deployment files, signed audit, docs-only admission record - none carries
     product behaviour or an API change (no /health change); the readiness-fix PR (step 0) is already merged (#624). One more is allowed ONLY to fix a NEW admission blocker the evidence finds (sec 0.4): that blocker
     only, a regression test where detectable, through the guard; if it changes deployable code the release is
     stale and the loop restarts at sec 0.5 step 2. The audit wins over the PR count. No new issue unless a separate
     public invariant.
 10. End per the FULL BRIEF's END. W7 is complete only when the post-admission record EXISTS as a #540 comment - a
     local copy is recovery evidence, not completion. Never call the programme finished before that, and never
     claim native branch protection.
```

---

## FULL BRIEF

### 0. Binding amendments (owner/consultant, 2026-10-29; the preparation-pass rulings of 2026-10-30 are §0.6 and supersede any conflicting wording here)

Here and throughout, **"owner" means the delivery/product decision owner — never the GitHub repository owner
`ashcochrane`**, who was unavailable and accepted nothing.

#### 0.0 The W7 governance exception

**The verified fact.** `ashcochrane/ubb` is a personal repository owned by `ashcochrane`. The acting account
(`ThePig96`) has `admin: false`, `maintain: false`. Updating ruleset `24574349` with
`R10-W7-REQUIRED-CHECKS-ruleset.json` answered **404**; classic protection answers 404. The effective rules on `main`
are `deletion` and `non_fast_forward` only. No repository admin was available.

**What is waived — for W7 and the first admitted `external` tenant ONLY:** the requirement that GitHub itself natively
enforce `test`, `contracts`, `codegen` and `code-builder-execution` on `main`. **Never claim they are natively
required.** Those four remain the intended native policy (`contract` is not part of it).

**Compensating control 1 — the R10 merge guard, extended through W7 only.** Every W7 PR that changes the repository
merges through `R10-merge-guard.py`, keeping its five exact-head checks (`test`, `contracts`, `contract`, `codegen`,
`code-builder-execution`) and its refusals: wrong base; draft or closed PR; a stale result (only the head SHA is read);
a missing or non-success result; a head that moved (`--match-head-commit`). No direct `gh pr merge`, no direct push.

**Compensating control 2 — deploy one exact, immutable release** (strengthened by §0.1).

**Compensating control 3 — re-verify immediately before admission** (strengthened by §0.1; done twice — §0.5 step 9
for the signed recommendation, and again as the first act of step 11, at the tenant-creation boundary).

**Compensating control 4 — the governance exception in the acceptance audit.** A short section records: repository
`ashcochrane/ubb`; native required checks not enforceable by the acting account; that account's lack of admin/maintain
authority; the refused ruleset/classic-protection write; the actual `main` protection **re-read at admission**; the
four intended native checks; the temporary W7 merge-guard controls; the exact deployed/admitted commit **and image
digest**; the CI evidence for that commit; and **the named human decision-maker who accepted the exception (LAUNCH
INPUT 6)** — never wording that implies `ashcochrane` accepted it. It must not say "required checks enforced". It
carries, or says the equivalent of:

> Native GitHub required-check enforcement was unavailable at admission because repository-admin access was not
> available. For this admission, exact-head CI verification, the R10 merge guard and exact-commit deployment were used
> as compensating controls. Native enforcement remains the intended repository configuration.

**Scope.** W7, the first real tenant in `external` billing mode, and the ordinary deployment/admission work to finish
the programme — nothing else. No payment capability is broadened: prepaid/postpaid and payment-rail activation stay
behind their rail gates. It authorises no weakened test, no CI bypass, no force-merge, and no admission of a build
whose exact commit or artifact cannot be proven.

**When admin access becomes available:** apply `R10-W7-REQUIRED-CHECKS-ruleset.json` and prove it with
`R10-W7-VERIFY-REQUIRED-CHECKS.py` plus a synthetic failing-check PR refused at merge. It is not a prerequisite for this
admission. No new ticket; the limitation is recorded in the audit and the W7 hand-forward material. Do not describe the
programme as having native branch protection until that is actually true.

#### 0.1 Release identity — the deployed image digest joins the exact-SHA evidence

A revision label proves what an image **claims** to contain; the digest proves which immutable artifact **ran**. W7
records, in one evidence file (`R10-W7-RELEASE-EVIDENCE.py`, `R10-W7-RELEASE-<sha8>.json`):

- the reviewed release commit SHA, and the source PR(s) that produced it;
- the exact-head CI evidence for that SHA (the five guard checks, each latest attempt per suite);
- the OCI label `org.opencontainers.image.revision=<sha>`, which must equal that SHA;
- the image repository/reference and its **immutable digest** (`sha256:…`);
- the host's deployment/release identifier, and the production target it names;
- proof that **web, Celery worker and Celery beat all run that same digest**.

Build the image **once** from the recorded SHA, push it, capture its digest, and deploy **that** artifact — by digest
(`repo@sha256:…`) wherever the host allows it. If the host exposes an immutable release/image ID instead, record the
mapping from that release to the digest. **A mutable tag (`latest`, a branch name) is never the admission identity.** A
later rebuild from the same Git SHA is a different artifact until proven otherwise; the tool refuses to record a second
digest for one SHA. Pre-admission verification proves both *deployed source revision == audited SHA* and *deployed
image digest == audited digest* for all three roles:

```
python R10-W7-RELEASE-EVIDENCE.py record   <sha>
python R10-W7-RELEASE-EVIDENCE.py artifact <sha> --image <repo> --docker <pushed ref>     (or --digest … --label …)
python R10-W7-RELEASE-EVIDENCE.py deploy   <sha> --release <id> --target <env> --web <d> --worker <d> --beat <d>
python R10-W7-RELEASE-EVIDENCE.py verify   <sha> --source <deployed sha> --release <id> --target <env> --web <d> --worker <d> --beat <d>
```

Read each runtime value from the host's own record of what is running, not from what was requested. No `/health` or
other API change is made to report any of it.

#### 0.2 SLOs — an applicable miss blocks admission

**If any SLO applicable to the external-mode admission misses its ratified target, STOP before tenant admission and
return the evidence for an owner/consultant ruling.** Never retarget, never invent a figure.

- **Before each measurement**, record the conditions #15 requires: the workload, the duration/sample count, the
  concurrency, the warm-up and steady-state treatment, and the applicable batch sizes. Those recorded conditions make
  the run authoritative.
- **Preserve the raw result/evidence of every authoritative attempt** (k6 output, server histograms), passing or not.
- **Do not** average away a failed run; discard an inconvenient attempt; silently rerun until green; or change
  concurrency, sample size, batch size or workload after seeing a result and call the new run authoritative. A run whose
  conditions were not recorded beforehand is not authoritative and is reported as such.
- **SLO 1's fault-window exclusion is fixed before the run, never chosen after a result.** #15 allows *"fault windows
  annotated, reported separately, excluded from the SLO"* — that authority stands, made reproducible here; it is not a
  new SLO. **Before the authoritative SLO 1 run starts**, record what qualifies as a fault window and how one will be
  identified. Then: preserve the raw data for the **full** run; annotate every excluded interval; report each excluded
  interval and its reason separately; compute the steady-state SLO on the permitted population only. **Never decide,
  after seeing a latency miss, that an interval was a "fault window" merely to remove it.** If an unexpected incident
  occurs that the pre-recorded criteria do not cover, preserve the run and bring the evidence back for an
  owner/consultant ruling rather than silently excluding it.
- The legs with no subject in `external` mode (top-up resumes, wallet floors, wallet-equals-history — and, by §0.6 F4,
  SLO 2's customer-wide `customer.stopped` and `customer.stop_cleared`) are **not applicable** to this admission and
  carry to rail activation or the relevant future capability exactly as ruled. **An inapplicable leg is never counted
  as a pass**, and no billing product, Stripe billing, customer wallet or payment behaviour is enabled merely to
  manufacture a subject for an SLO.
- **SLO 1 runs first** on the real host (§0.6 F7) — before SLO 2, SLO 3 or the acceptance audit — at the required batch
  sizes including 100 items. If any applicable SLO 1 leg misses, STOP W7 there and return the authoritative evidence.
- **SLO 2's observation boundary is the client's receipt** (final refinement 1). The ratified target is *crossing →
  webhook received by the client, p99 ≤ 5 s* — not "event persisted" and not "dispatch began". For this admission the
  applicable stop webhooks are `task.killed` and `subtask.killed` (§0.6 F4); the target is unchanged. Measure it with a
  **controlled external webhook receiver standing in for the client boundary**. Each authoritative sample records: the
  correlated crossing/stimulus; the webhook type and its correlation/idempotency identity; the time the receiver
  **actually accepted** the webhook; and the measured crossing-to-receipt latency. **Never substitute** internal event
  creation time, queue enqueue time, Celery task start/finish, the outbound HTTP send time, or any database/audit
  timestamp for client receipt. Measure stimulus and receipt on **one controlled clock** where practical (the harness
  that issues the crossing also hosts, or reads the receive time from, the receiver); if separate clocks are
  unavoidable, record how synchronisation and skew were bounded. **#15's in-band verdict assertion stays separate**
  — it is never folded into the webhook p99.
- **SLO 3: W7 runs the ratified SLO 3 profile unchanged for every applicable external-mode leg; the explicitly ruled
  rail-only legs are omitted from execution and reported as not applicable, never as passes.** The one authoritative
  **external-mode execution profile** is in §3, with the verbatim ratified source beside it so the adaptation is
  auditable — no execution-time lookup, no reinterpretation, and no invented operation standing in for an omitted one.

#### 0.3 Pre-admission data — the real client is not a test tenant

Deployment, SLO measurement and the audit exercises all happen **before** the real tenant is admitted, so none of them
may quietly onboard the first client.

- Use **one clearly identified non-customer pre-admission tenant** (its name says so) and controlled test data for
  every SLO and audit scenario needing tenant activity. Record its identity in the audit.
- **Never run `seed_dev_data` in the production environment.**
- Create no production economics that could be mistaken for the first customer's records.
- The real first tenant is created **only in O2**, after the release artifact is fixed, the applicable SLOs have
  passed, the audit has reached an admission recommendation, and the release evidence is re-verified (§0.5).
- **If a specific SLO inherently requires the real client** rather than controlled pre-admission traffic, STOP and
  identify that dependency; never admit the customer early to satisfy it.
- **Evidence hygiene, before any substantial SLO/audit data is generated:** identify — from current code, not from a
  name — how the pre-admission tenant is kept distinguishable from real customer data, and record what happens to it
  after admission (kept and labelled, deactivated, or removed, and how). **Do not assume a "sandbox" flag has exclusion
  semantics unless current code proves it**: `Tenant.is_sandbox` (F4.4, `apps/platform/tenants/models.py`) marks a
  *sibling* of a parent tenant routed to the rail's `test` environment — read every reader of it before relying on it
  for anything else. This is evidence hygiene, not a new product rule.

#### 0.4 The acceptance audit — blockers versus accepted limitations; the actual decision-maker

**An unresolved finding blocks admission** — until fixed and re-verified, unless the owner/consultant explicitly
rules otherwise on that specific evidence — when it affects any of:

- tenant isolation / authorisation;
- economic correctness or truthfulness;
- loss or duplication of customer usage or economic records;
- admission/control enforcement;
- materially false public API or SDK behaviour;
- the inability to prove which release is deployed.

**The audit wins over the desired PR count.** W7 has **four planned PRs** — the readiness-fix PR (§0.5 step 0: the
product fixes §0.6 rules, and nothing else — **merged pre-FINAL as #624 → `1bf0c0ca`, 2026-11-02**), the deployment
files, the signed audit, the docs-only admission record — and "no product behaviour" applies to the last three. **An additional fix PR is permitted only when W7 evidence
discovers a NEW admission blocker that must be corrected before continuing**, and then:

- it fixes that blocker and nothing else — no speculative cleanup, no unrelated improvement;
- no new issue, unless the defect genuinely proves to be a separate public invariant;
- it carries a regression test wherever the defect is mechanically detectable (ADR-0008 §8);
- it merges through the W7 merge guard;
- **if it changes deployable code, the recorded release is stale**: loop back through release recording, build,
  deploy and the relevant SLO proof from §0.5 step 2 (and re-run the audit scenarios it affects) before continuing.

**Accepted limitations are only non-blocking operational/hardening items**, and the already ruled ones are: #472; native
GitHub required-check enforcement (§0.0); chaos drills; the SLO legs inapplicable to this admission (carried to rail
activation or the relevant future capability — §0.6 F4). Nothing else becomes an "accepted limitation" without an
explicit owner/consultant ruling — in particular none of the preparation findings F1–F8 is one (§0.6).

**Names.** The audit records the **named decision-maker who accepted the W7 exception and the admission risk (INPUT
6)** and the **named acceptance-audit signer (INPUT 4)** — stating explicitly whether they are the same person.

**What the signed audit says — and what it must not** (final refinement 3). The audit is signed at step 8, before the
real tenant exists, so it is an **admission recommendation/authorisation**: in substance, *the reviewed release
satisfies the applicable pre-admission evidence and is approved for the controlled admission steps, subject to the
mandatory step-9 re-verification.* **It never claims O2 has happened** — no "the tenant has been admitted", no tenant
activity, no future fact. What actually happened at admission goes in the separate **post-admission result record**
on #540 (§0.5 step 15). If the repository audit document should also carry the outcome, that is a **docs-only addendum
after admission**, in the admission-record PR (§0.5 step 14) and clearly dated after the signature — never an edit to
the signed text.

#### 0.5 The admission sequence — the irreversible boundary is step 11; the repository records it only at step 14

The order carries the semantics: the audit **recommends** (step 8), admission **happens** (steps 11–13), and only then
does the repository **record** that it happened (step 14) and #540 receive the result (step 15).

0. **The W7 readiness-fix PR** (§0.6) — **DONE PRE-FINAL**: #624, four staged commits (F1+F2, F3, F5, F6, each with
   its ruled regression tests), merged through the W7 merge guard on 2026-11-02 at head `6e708b29` → `main` =
   `1bf0c0ca`, under the owner/consultant sequencing amendment of 2026-11-02. The real W7 verifies it is on `main`
   (P0(f)) and begins at step 1. **No release is recorded, built or deployed from a commit that lacks it.**
1. The deployment-files PR merges through the W7 merge guard.
2. Record the exact release SHA and its check evidence (`… record <sha>`), after that merge's `main` push run is green
   — a SHA that contains the merged readiness fixes. `record` refuses a SHA whose evidence already names an artifact
   (§0.6 F8); a deliberate restart uses a fresh evidence directory.
3. Build the one OCI image from that SHA (revision-labelled), push it, record its digest (`… artifact`).
4. Provision and configure the production environment on the host (LAUNCH INPUTS 1–3): managed Postgres 16 and
   Redis 7; secrets only through the host's secret/configuration mechanism; `UBB_MEASUREMENT_RETENTION_DAYS=400`; the
   log drain; owner alerting on `live_counter.drift_spike` (and prepaid's `wallet.drawdown_repair_spike`, dormant in
   `external` mode) to **exactly the destination in LAUNCH INPUT 7** — configured through the host's
   environment/notification mechanism, **never written into a committed deployment file** where the address is
   configuration or private data. The §0.6 F9 runbook facts bind the host configuration. No `CELERY_BROKER_URL`
   workaround (F1 is fixed in the product), and no placeholder Stripe secret merely to make W7 pass (F5 fails closed);
   a real Stripe secret arrives only if Stripe/payment capability is later activated, through the host's mechanism.
5. Run the database migration **once**, as an explicit release operation, from that image, on the fresh database.
6. Start web, worker and beat from the **same image digest**; record the host release and the three roles (`… deploy`).
7. Run the applicable SLOs against the deployed release on controlled pre-admission data (§0.2, §0.3) — **SLO 1 first**
   (§0.6 F7), including 100-item batches, after every web worker is warmed; **if any applicable SLO 1 leg misses, STOP
   W7 here** and return the authoritative evidence. Only if SLO 1 passes: SLO 2 (`task.killed`, `subtask.killed`, and
   the separate in-band verdict) and SLO 3 (the §3 external-mode profile).
8. Perform the acceptance audit (§0.4; §3 below) and obtain the named signer's decision — an **admission
   recommendation/authorisation**, never a claim that admission happened.
9. **The pre-recommendation re-verification** (its evidence belongs to the signed recommendation): re-read the actual
   GitHub protection on `main` for the audit; run `… verify` (it must print `ADMISSION RE-VERIFIED`) with the source
   revision, the release, the target and all three roles' digests read live from the host; and confirm the deployed
   database/environment is the intended production target. Step 10's PR cycle follows, so this is **not** the last
   check before admission — step 11 repeats it.
10. Merge the **signed-audit PR** through the W7 merge guard. It contains the signed pre-admission audit
    (recommendation) and the release evidence — and **does NOT delete the dated compatibility note**. **If it changes
    deployable application behaviour rather than documentation/evidence only, the audited release is stale: STOP** and
    re-record, redeploy and re-measure as appropriate.
11. **Only after that PR is on `main`**, and **beginning with a final live re-verification as its first act**:
    re-read from the host the deployed source SHA, the host release ID and target environment, and the web, worker and
    beat image digests, and run `… verify` again with those live values. **It must print `ADMISSION RE-VERIFIED`; if
    anything differs from the audited release, STOP — do not admit.** Then, at the tenant-creation boundary itself,
    create the real first tenant (INPUT 5) through the ruled operator path (§0.6 F10) — an operator-run Django shell
    (a one-off invocation of the release image) using the existing Django model/service APIs, **never raw SQL** — mint
    the client's first API key with `TenantApiKey.create_key`, hand the key and the #561 widget secret to the client
    through an out-of-band secret channel only, and re-confirm on the created tenant that `billing_mode = external`
    and no payment rail is activated. The bootstrap procedure is recorded by command/API names only — no secret value. This second check
    does not rewrite the signed audit; the #540 record (step 15) states that the mandatory final re-check passed.
12. Exercise a minimal real-client end-to-end path proving the tenant is actually using UBB, including the ruled
    end-customer usage summary (#561) — on the path the final factual review bound (P2 if the client integrates
    through SDK v5, otherwise P1; P3 where a real Task lifecycle is representative; webhook push supplementary, never
    the sole proof): client action → authoritative UBB processing/persistence → supported client-visible readback →
    the #561 usage-summary proof. A health check or a database row alone is not client acceptance.
13. Hand the client the exact `sdk-v5.0.0` wheel, `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256
    `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948` (`R10-SDK-V5-RELEASE/`). It is the released SDK matching the
    current v5 contract (annotated tag `sdk-v5.0.0` dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`; reproducibly built
    and independently verified); it is handed over by file; it is not published to PyPI. **FINAL owner/consultant
    ruling, 2026-11-09** — supersedes the older W7/R2 instruction to hand the first client SDK v4 (`sdk-v4.0.0`,
    `R10-W6-RELEASE/`): `main` publishes the v5 contract after Stage C5's one deliberate pre-live breaking regeneration,
    and SDK 4.x does not match it.
14. **Once steps 11–13 have succeeded**, merge one tiny **docs-only admission-record PR** through the W7 merge guard:
    it deletes the dated pre-admission note from `docs/api-compatibility.md` (`:10`, the *"Status, as of 2026-07-28"*
    block) — that deletion is the repository's admission record (ADR-0007 §5), made only after admission actually
    happened — and may add the clearly post-admission addendum to the audit document (§0.4), never editing the signed
    text. **No deployable code.** Being docs-only, it does not make the deployed release stale; **if it contains any
    deployable application or API behaviour, STOP** — the release identity rules (§0.1) apply again.
15. **Post the post-admission result record as ONE comment on #540** (the durable operational record; no new issue),
    recording: the actual tenant identity; the actual admission date and time; that the mandatory final re-check at
    step 11 printed `ADMISSION RE-VERIFIED` (with the live values it read); the admitted mode, `external`; that no
    payment rail was activated; the bootstrap procedure by command/API names only (no secret value); the exact release
    SHA; the image digest **still running** (re-read from the host); the
    successful minimal real-client end-to-end exercise; the #561 proof; the SDK wheel's filename and SHA-256 and its
    handover; a link to the signed acceptance audit; and the **final five-line report**, which closes the comment and
    is the window's final report to the owner. **The #540 comment is the authoritative post-admission record.** If the
    classifier refuses the GitHub write, save the exact text in the project folder (`R10-W7-POST-ADMISSION.md`) and
    hand the delivery owner the exact `gh issue comment 540 --body-file …` command — but **W7 is then NOT complete
    until the delivery owner has posted it and the comment is confirmed to exist on #540.** A local prepared copy is
    recovery evidence, never completion evidence; the programme is never called finished while the admission result
    exists only on one machine.

**Never commit a production secret value** to Git, a PR body, an audit document or a log.

#### 0.6 The preparation-pass rulings (owner/consultant, 2026-10-30) — supersede any conflicting W7 wording

The W7 preparation findings (`R10-W7-PREP/findings.md`, F1–F10, evidence in `R10-W7-PREP/evidence/`) are **accepted
as valid evidence for planning the real W7**. They are not admission evidence: the real W7 re-derives what it reuses.
Do not reopen W6; create no new issue. These rulings supersede any W7 wording that conflicts with them.

| Finding | Classification | Where it is handled |
|---|---|---|
| F1 web process not bound to the configured Celery app | **fix before deploy** (blocker confirmed) — **DONE PRE-FINAL** (#624) | remedy (a), the product fix: `config/__init__.py` |
| F2 two scheduled tasks unregistered / unroutable | **fix before deploy** — **DONE PRE-FINAL** (#624) | `config/celery.py` `app.conf.imports` |
| F3 wallet-policy hard floor applied to `external` | **fix before deploy** (blocker confirmed) — **DONE PRE-FINAL** (#624) | `flags.py::holds_a_wallet` at every wallet leg |
| F4 SLO 2 customer-wide legs have no `external` subject | **SLO scope ruling** | §0.2, §3 table and profile, LAUNCHER |
| F5 live Stripe webhooks verify an empty secret | **fix before deploy** (blocker confirmed) — **DONE PRE-FINAL** (#624) | both live receivers fail closed |
| F6 accumulator first-insert race | **fix before deploy** — **DONE PRE-FINAL** (#624) | savepoint + exact-once fallback |
| F7 SLO 1 per-item cost at large batches | **production gate** (not a blocker yet, not waived) | §0.5 step 7: SLO 1 first; a miss STOPS W7 |
| F8 release-evidence `record` re-run erases the artifact | **fix before deploy** — done pre-FINAL (project-folder tool) | applied and re-validated 2026-10-30 |
| F9 deployment-shape facts | **runbook only** (binding) | deployment files (step 1) and host verification |
| F10 operator bootstrap and the #561 secret handover | **runbook only** (binding) | §0.5 step 11 and step 15 |

**F1 — BLOCKER CONFIRMED: the product fix, not the deployment workaround.** Remedy F1(a). The web process loads UBB's
configured Celery application through the conventional Django/Celery wiring; do not rely on setting
`CELERY_BROKER_URL` merely so Celery's default app happens to publish (that would leave two Celery configurations and
make correctness depend on process-specific environment behaviour — UBB has ONE configured Celery app). The fix must:
make the Django/web import path bind `shared_task` to the configured UBB Celery app; add a regression test proving
the web path resolves the configured app/broker; prove a representative web-side `.delay()` reaches the intended
broker without `outbox.dispatch_failed`; preserve the outbox sweep as resilience, not the normal delivery mechanism.
Deployable code: it lands before the release SHA is recorded.

**F2 — FIX, in the same Celery readiness work.** Not accepted as a production limitation. `core.tasks.
flush_api_key_last_used` and `apps.platform.events.tasks_webhook_cleanup.cleanup_webhook_delivery_attempts` must be
registered by the real worker, and the beat schedule must route them to a queue the real worker consumes. Prefer
deterministic application/task registration over a deployment-only `--include` plus consumption of the otherwise stray
default `celery` queue. Regression coverage proves both scheduled task names are registered and routable. No general
Celery cleanup.

**F3 — BLOCKER CONFIRMED: `external` mode has no wallet-policy subject.** The earlier architectural ruling stands:
wallet-floor enforcement has no subject for an `external` tenant, and an absent wallet is never a zero-balance wallet.
For `billing_mode = external`: wallet-policy / hard-floor evaluation does not run; a priced usage event cannot create a
`wallet_policy` stop episode because there is no wallet; it cannot suspend the customer for that nonexistent wallet;
`enforcement_mode = enforcing` stays usable for the controls that genuinely apply in `external` mode, including Task and
Subtask ceilings. Do NOT solve it by forbidding `external` tenants from selecting `enforcing`. Regression tests cover at
least: external + enforcing + priced event → no `hard_floor` customer stop; no wallet-policy episode; the customer is
not suspended by the nonexistent wallet; the applicable Task/Subtask enforcement still works. A clean pre-launch fix —
no compatibility or data repair (no production tenant has been admitted).

**F4 — SLO SCOPE RULING: the customer-wide legs are carried forward.** Never enable the billing product, Stripe
billing, a customer wallet or any payment behaviour merely to manufacture an SLO subject. For this first `external`
admission, SLO 2 is: **applicable now** — `task.killed` webhook latency, `subtask.killed` webhook latency, and the
associated in-band stop verdict, separately as already ruled; **not applicable, carried to the relevant future
capability / rail activation** — customer-wide `customer.stopped`, customer-wide `customer.stop_cleared`, the resume
after a top-up. An applicability ruling, not a changed target: wherever an applicable stop webhook exists, crossing →
client receipt p99 ≤ 5 s is unchanged. No customer-wide `external` equivalent is invented. (§0.2, §3 and the LAUNCHER
no longer claim that a non-top-up customer-wide clear must be driven.)

**F5 — BLOCKER CONFIRMED: live Stripe webhooks fail closed.** Not "we will always configure a secret": the product
boundary itself fails closed when `STRIPE_WEBHOOK_SECRET` is missing or blank — before calling Stripe signature
verification or persisting a webhook event, detect it, refuse the live webhook, persist nothing from that request. Use
an existing appropriate refusal/error pattern; no new public vocabulary for this. Regression tests prove: unset secret
→ refused, no webhook-event persistence; blank secret → refused, no persistence; wrong signature with a configured
secret → refused; correct signature with a configured secret → accepted. No fake Stripe secret is required for the first
`external` tenant; a real one is supplied through the host's mechanism only if Stripe/payment capability is activated.

**F6 — FIX before first admission.** The dead PostgreSQL fallback is not carried into production. Invariant: concurrent
first events for one customer can neither abort economic accumulation nor double-count it. Fix the transaction /
savepoint / upsert behaviour so the losing concurrent insert resolves the already-created accumulator and applies its
increment exactly once. A regression test exercises the concurrent first-insert case on PostgreSQL. No accumulator
redesign.

**F7 — PERFORMANCE RISK: not yet a blocker, not waived.** Do not change the 200 ms SLO and do not optimise speculatively
from the local number. On the real host run SLO 1 FIRST — before SLO 2, SLO 3 or the acceptance audit — exercising the
required batch sizes including 100 items. If any applicable SLO 1 leg misses its ratified p99: STOP W7 and return the
authoritative production evidence — never retargeted, averaged away, or called an accepted limitation. If it passes,
continue.

**F8 — MUST FIX before any real release evidence is recorded — DONE 2026-10-30.** The authoritative tool is
project-folder tooling (not repo-tracked), so it was patched pre-FINAL: once an evidence record names an
artifact/digest, `record` refuses (writing nothing) instead of erasing that state and reopening the SHA. Re-validated
on the authoritative tool against a scratch directory (`R10-W7-PREP/release-evidence-dryrun/
F8-validation-transcript.json`): initial record works; the artifact digest is recorded; re-running `record` is refused
and cannot erase or replace it; a second build/digest for the same SHA is still refused; the evidence JSON is
byte-identical after every refused operation; `deploy` and `verify` still work. Tool SHA-256 `ea7ef84e…` → `e870d550…`.

**F9 — runbook facts, binding** on the deployment-files work and host verification: build from a context that
includes the repository-level `openapi/error-codes.json`; pin/provide the production WSGI server explicitly (never an
undeclared host/global package); never copy a `.env` file into the production image; configure the host's health/proxy
behaviour so the HTTPS redirect does not make health checks falsely fail — without changing the public API for it; warm
every web worker before authoritative SLO measurement; exactly one Celery beat replica; a writable beat schedule
location where required; explicit worker queues; prove the log drain receives both the web JSON logs and the Celery
logs. The unstyled Django admin and the runtime test packages are not admission blockers; do not broaden W7 to
redesign either.

**F10 — bootstrap, runbook.** No tenant-creation API and no Django admin form fix for W7. For the first admission an
operator-run Django shell is the path, using the existing Django model/service APIs, never raw SQL; the first client
API key comes from `TenantApiKey.create_key`. The #561 widget secret is a secret, handed to the client through an
appropriate out-of-band secret channel, and never appears in Git, PRs, the acceptance audit, preparation artifacts or
#540. The bootstrap procedure is recorded by command/API names only, with no secret values.

**Client golden path — `CLIENT GOLDEN PATH READY` accepted.** No traditional UI is built to prove admission. The final
factual review binds step 12 to the real client's actual supported integration: P2 if SDK v5 (RULED 2026-11-09); otherwise P1 for a
direct API integration; P3 where a real Task lifecycle is representative; webhook push supplementary, never the sole
proof. The minimal admission proof: client action → authoritative UBB processing/persistence → supported client-visible
readback → the #561 usage-summary proof. A health check or a database row alone is not client acceptance.

**The ONE W7 readiness-fix PR (§0.5 step 0)** — an explicit amendment to the earlier blocker-fix-PR rule. Staged
commits inside one PR: Celery wiring/registration (F1 + F2); external wallet applicability (F3); Stripe webhook fail-
closed (F5); accumulator concurrency (F6); F8 is not in it (already applied to the project-folder tool). F2 and F6 are
included because preparation proved concrete defects before first admission; this authorises those two findings
specifically and no general cleanup. The PR fixes only these ruled findings, adds the regression tests above, merges
through the W7 merge guard, carries no unrelated refactor and creates no new issue. Only after it is merged and `main` is
green does W7 proceed to the deployment-files PR and then record the release SHA. Never record or build the production
release from the known-bad pre-fix commit.

**Sequencing amendment (owner/consultant, 2026-11-02) — executed.** The ruled fixes were known, bounded,
regression-testable and independent of the seven inputs, so exactly ONE pre-FINAL readiness-fix PR was authorised and
merged through the temporary W7 merge guard while STATUS stayed PRE-LAUNCH — NOT FINAL (an exception limited to that
PR): **#624**, staged commits F1+F2 / F3 / F5 / F6, head `6e708b29`, squashed to `main` = `1bf0c0ca`. After the merge
the ruled regression tests and the targeted local probes were re-run and recorded as **PRE-LAUNCH READINESS EVIDENCE —
NOT ADMISSION EVIDENCE** (`R10-W7-PREP/readiness/`). This is not production W7 having started: no provider, no
production resource, no deployment, no release recorded or built, no authoritative SLO, no audit, no tenant, no
compatibility-note deletion, no FINAL.

**Before FINAL:** STATUS stays PRE-LAUNCH — NOT FINAL; the seven LAUNCH INPUTS stay blank until supplied; F8 is applied
and re-tested (done); step 0 is done (above). The remaining gate is the seven real launch inputs and the final factual
review; then the fresh W7 session starts at §0.5 step 1, the deployment-files PR.

### 1. Why — the finish line

"Finished" (R2, as amended by §0.0) means all of the following hold:

- UBB is deployed — one recorded artifact, by digest;
- **the ruled CI checks passed on the exact admitted release, enforced through the temporary W7 release controls;
  native GitHub enforcement is an explicitly accepted temporary governance limitation** (this replaces "the required
  `main`-branch checks are enforced" for this admission);
- the applicable SLOs have been measured and **met** (§0.2);
- the acceptance audit is signed, with no unresolved blocker (§0.4);
- a real first `external` tenant has been admitted and is using UBB;
- #561's end-customer usage summary works for that tenant (restored in W5);
- the repository records the admission (the dated note deleted after it, §0.5 step 14), and the post-admission result
  record **exists on #540** (§0.5 step 15) — not only as a local file.

**Payment-rail activation is not part of it.**

### 2. What binds this window

**The owner's close-out direction of 2026-10-22, approved with amendments in the owner and consultant's review the
same day** (`R10-W0-190-SPEC-PROMPT.md` §R):

> W7 — one operational close-out window: deploy UBB, measure the three SLOs against the real current endpoints, run
> the ADR-0008 acceptance audit, and make the admission decision.

**From R2:**

> Hosting: one application image deployed as separate web, Celery-worker and Celery-beat process roles, backed by
> managed Postgres and Redis.
>
> The other W7 defaults are approved: host log drain + accountable-owner email for the current alerts; SDK v4 tag plus
> reproducibly built wheel for the first client; chaos drills recorded as an explicit accepted limitation and first
> post-admission hardening item, not silently discarded.

**SUPERSEDED FOR FIRST-CLIENT SDK HANDOFF by the FINAL owner/consultant ruling of 2026-11-09: use `sdk-v5.0.0` and its
verified wheel (`ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`,
`R10-SDK-V5-RELEASE/`; §0.5 step 13). The R2 text above is preserved as provenance only. The remaining R2 defaults
continue to stand unless separately superseded.**

**The governing documents:** ADR-0008 §6, §8 and §9; ADR-0007 §5; #158 §9 and §10; #15's resolution (the three SLO
numbers and their test conditions); the #190 spec, part 4; **§0 above**, which binds over anything older here.

### 3. What each part of the sequence must contain

**Deployment files (step 1).** The container definition, plus the host's configuration for three process roles — web
(gunicorn/uvicorn), Celery worker and Celery beat — from **one** image carrying the revision label. One PR, merged
through the guard, on a `main` that already contains the readiness-fix PR (#624, step 0, done). No product behaviour (a NEW admission-blocker fix, if the
evidence requires one, is a separate PR under §0.4's rules). The §0.6 F9 facts bind it: a build context that includes
`openapi/error-codes.json`; an explicitly pinned WSGI server; no `.env` in the image; health/proxy configuration that
keeps the HTTPS redirect from failing health checks (no public-API change for it); one beat replica with a writable
schedule location; explicit worker queues. The draft in `R10-W7-PREP/image/` is preparation input, re-derived here.

**The SLOs (step 7; §0.2).** The ratified sources are copied here **verbatim** so the run never depends on reading an
old issue mid-production: #15's resolution (comment `4979770864`, 2026-07-15), #10's fixed assertions as delivered to
#15 (`4960420988`), #13's rider (`4970990205`), #18's post-close amendment (`4979814383`), and #190 spec part 4 §2
(`6353327113`), which restates them against today's endpoints. All tenant activity is on the pre-admission tenant
(§0.3). Record each run's conditions **before** it starts (§0.2). **Order (§0.6 F7): SLO 1 first; a miss STOPS W7;
only then SLO 2 and SLO 3.** The preparation harness (`R10-W7-PREP/harness/`, `06-slo-harness.md`) is input to be
reviewed and re-derived, never authoritative as it stands.

- **SLO 1 — the recording path.** #15: *"Accept-path SLO — ingest POST p99 <= 200ms at any batch size up to 100 items;
  measured client-side by k6 and cross-checked against server-side histograms; steady-state only (fault windows
  annotated, reported separately, excluded from the SLO)."* Spec part 4 §2 restates the subject: `POST
  /api/v1/metering/usage`, and `POST /api/v1/metering/usage/batch` at 1–100 items — **p99 ≤ 200 ms per request**,
  client-side k6 cross-checked against server histograms, steady state only. Record the batch sizes measured — they
  include 100 items (§0.6 F7); UBB records no request-latency histogram, so the server-side cross-check reads the
  host's/WSGI server's per-request timing (the preparation pairs it with k6 per request by correlation id). The
  fault-window exclusion #15 allows is applied **only** by the criteria recorded before the run (§0.2). The
  recorded substance change (an asynchronous accept → a batch recording each item synchronously in its own commit) is
  part of the evidence, whatever the result.
- **SLO 2 — signal latency.** #15: *"Signal-latency SLO (the number #10 delegated here) — crossing event lands -> stop
  webhook received by the client, p99 <= 5s; same threshold for the resume webhook after top-up. The in-band channel
  (the next API response already carries the stop verdict) is asserted separately as effectively immediate."* #18's
  amendment: *"the resume-latency SLO now pairs with the stop.cleared event #18 spec'd"*. Spec part 4 §2: the stop
  webhook is `customer.stopped` / `task.killed` / `subtask.killed`, **p99 ≤ 5 s**, and the same threshold for the clear
  (`customer.stop_cleared`). Measured at the **client's receipt** exactly as §0.2 pins it. The in-band verdict on the
  recording response is a **separate** assertion ("effectively immediate"), reported on its own. **Applicability for
  this admission (§0.6 F4):** `task.killed` and `subtask.killed` are applicable; customer-wide `customer.stopped`,
  customer-wide `customer.stop_cleared` (by any path) and the resume after a top-up are **not applicable — carried** to
  the relevant future capability / rail activation; the target is unchanged wherever an applicable stop webhook
  exists. The controlled receiver needs a public DNS name, a publicly trusted TLS certificate and a public address —
  UBB delivers only to public https (re-checked at every send).
- **SLO 3 — the load storm. The ratified source, verbatim** — kept as evidence so the adaptation below is auditable;
  it is **not** executed as written, because it includes legs this admission has no subject for: *"Load-storm profile (for when the load leg
  is built) — 1 hour sustained at 500 events/s: 80% batch requests (sizes 10-100) / 20% single-event, ~5% deliberate
  duplicate replays; one tenant, ~200 customers including business+seat hierarchies; ~20 choreographed cap/floor
  crossings and top-up resumes mid-storm; run-capped runs and per-task caps exercised; 10-minute drain window, then the
  fixed assertions (zero events lost/mis-attributed/mis-tagged; for every wallet touched, `Wallet.balance_micros` == sum
  of its `WalletTransaction` history, per the ADR-002 rider); plus one short unasserted spike to 1000 events/s, observed
  for headroom only."* The completeness assertion's ratified wording (#10, via `4960420988`): *"Completeness (hard
  pass/fail): under ~5× peak (~500 eps) with cap and floor crossings mid-storm, zero events lost, mis-attributed, or
  mis-tagged (past-limit stop-context tags included). Pure counting, no cost estimation."* The wallet rider (#13, via
  `4970990205`; the source's backslash quoting rendered as code): *"the proof plan must include a hard pass/fail
  ledger-agreement assertion — for every wallet touched, `Wallet.balance_micros` == sum of its `WalletTransaction`
  history, checked at the end of the load storm and at the end of the soak. Any drift, even one micro-unit, fails the
  run."* (#18 dropped the soak leg: *"the >=1-week advisory soak leg drops with it"*.) #10 also fixed one quantity as
  **observed, never asserted**: *"worst negative balance reached — evidence for the guarantees doc, never a promised
  bound."*

**SLO 3 — the authoritative external-mode execution profile.** W7 runs the ratified SLO 3 profile unchanged for every
applicable external-mode leg; the explicitly ruled rail-only legs are omitted from execution and reported as not
applicable, never as passes. This storm, and nothing else, is the one W7 executes:

- **1 hour sustained at 500 events/s;**
- **80% batch requests, sizes 10–100; 20% single-event;**
- **~5% deliberate duplicate replays;**
- **one tenant — the pre-admission tenant (§0.3) — with ~200 customers including business/seat hierarchies;**
- **the applicable cap crossings — the Task and Subtask COGS-ceiling crossings (§0.6 F4)** — choreographed mid-storm;
  no customer-wide crossing and no customer-wide clear;
- **run-capped runs and per-task caps exercised;**
- **a 10-minute drain window;**
- **then the hard completeness assertion: zero events lost, zero mis-attributed, zero mis-tagged — past-limit
  stop-context tags included** (pure counting, no cost estimation);
- **one short spike to 1,000 events/s, observed for headroom only — never asserted.**

**Omitted from this admission's executable storm, and each reported as `not applicable — carried to rail activation`:**
the wallet-floor crossings; the top-up resumes; the wallet ledger-agreement assertion (`Wallet.balance_micros` == sum of
its `WalletTransaction` history). **Also omitted, reported `not applicable — carried to the relevant future capability /
rail activation` (§0.6 F4):** the customer-wide crossings (`customer.stopped`) and every customer-wide clear
(`customer.stop_cleared`).

**No invented equivalents.** The omitted operations are not replaced to preserve a count such as "~20 crossings". Before
the run, W7 inspects current code (the fixed release) and **states the actual applicable choreography** — the Task and
Subtask ceiling crossings (and any parent-ceiling cascade) it will drive, and how many of each — and records that
statement with the run's other conditions (§0.2); `R10-W7-PREP/05-slo-choreography-external-mode.md` is preparation
input to that statement, re-derived on the fixed release. No customer-wide crossing or clear is driven, and no
billing/payment behaviour is enabled to create one. Whatever count results is the count.

**What applies to this `external`-mode admission, and what is carried** (spec part 4 §2: *"Carried to rail activation,
not dropped. These have no subject for an `external` tenant: the top-up resumes in SLO 2's clear leg; the wallet-floor
crossings in SLO 3's choreography; SLO 3's assertion that each wallet's balance equals its transaction history. They
are measured when a payment rail is activated."*):

| Leg | This admission |
|---|---|
| SLO 1, both routes, 1–100 items | **applicable** |
| SLO 1 runs first; a miss STOPS W7 (§0.6 F7) | **applicable** — ordering gate |
| SLO 2 stop webhooks `task.killed` and `subtask.killed` | **applicable** |
| SLO 2 customer-wide `customer.stopped` and `customer.stop_cleared` (every path, top-up or not) | carried to the relevant future capability / rail activation (§0.6 F4) |
| SLO 2 resume after a top-up | carried to rail activation |
| SLO 2 in-band verdict ("effectively immediate") | **applicable**, asserted separately |
| SLO 3 external-mode execution profile (above): rate, mix, duplicates, ~200 customers with business/seat hierarchies, the Task and Subtask ceiling crossings (counted from current code, not padded toward ~20), run-capped runs and per-task caps, 10-minute drain | **applicable** |
| SLO 3 customer-wide crossings and clears | carried to the relevant future capability / rail activation (§0.6 F4) |
| SLO 3 completeness: zero events lost, mis-attributed or mis-tagged (past-limit stop-context tags included) | **applicable — hard pass/fail** |
| SLO 3 floor crossings and top-up resumes in the choreography | carried to rail activation |
| SLO 3 wallet ledger-agreement (`Wallet.balance_micros` == sum of its `WalletTransaction` history) | carried to rail activation |
| SLO 3 spike to 1,000 events/s | observed for headroom only — never asserted |
| Worst negative balance | observed only where it has a subject, never asserted |

A carried leg is reported as **not applicable**, never as a pass. **Any miss on an applicable leg: STOP before
admission**, with the evidence (§0.2).

**The acceptance audit (step 8; O1).**
- The record carries #158 §9.2's fields — date, auditor (the named signer, INPUT 4), the commit **and image digest**
  and the new API baseline (`api-v1-cutover`), the documents and ADRs reviewed, the gates relied upon, the manual
  scenarios exercised, the known accepted limitations — plus the governance exception section (§0.0 control 4) and
  the named decision-maker (INPUT 6).
- It carries ADR-0008 §9's sentence **verbatim**.
- **The scenarios**, run on the pre-admission tenant (§0.3), cover #158 §9.1's questions: does economic value travel
  correctly end to end; are `unknown`, `waived`, `not_applicable` and `incomplete` displayed honestly; does the Code
  Builder produce a coherent integration; are permissions correct; are old terms gone; are the migration, the audit
  reset and the baseline rotation complete.
- **Blockers versus limitations** exactly as §0.4. The accepted limitations: #472; native GitHub required-check
  enforcement (§0.0); chaos drills; the SLO legs inapplicable until rail activation.

**Admission (steps 9–15; O2).**
- The signed-audit PR (step 10) carries the signed pre-admission audit and the release evidence, and does **not** touch
  the dated compatibility note.
- No route creates a tenant: create it through the ruled operator path (step 11; §0.6 F10) — an operator-run Django
  shell using the existing model/service APIs, never raw SQL; the first key via `TenantApiKey.create_key`; the key and
  the #561 widget secret to the client out of band only; the procedure recorded by command/API names only.
- Confirm the tenant is using UBB on the bound integration path, including the widget's usage summary (step 12); hand
  over the wheel (step 13).
- **Only after steps 11–13 succeeded**, the docs-only admission-record PR (step 14) deletes the dated note in
  `docs/api-compatibility.md` (`:10`, the *"Status, as of 2026-07-28"* block) — that deletion **is** the repository's
  admission record (ADR-0007 §5) — with the optional post-admission audit addendum; no deployable code.
- Post the post-admission result record on #540 (step 15); W7 is complete only when that comment exists on #540. The
  signed audit stays a pre-admission recommendation.
- **Tick #540's admission lines.** #540 then holds only the per-rail section: #472 and per-rail activation, behind its
  gate.

### 4. Where the audit record lives

- **The signed acceptance audit** (the admission recommendation): a dated document under `docs/` — for example
  `docs/acceptance/<date>-platform-admission.md` — in the signed-audit PR (step 10), with the release evidence file's
  contents (no secret in it), and a pointer on #540. It never says admission happened.
- **The repository's admission record:** the deletion of the dated compatibility note, in the docs-only
  admission-record PR (step 14), after admission — with the optional post-admission addendum to the audit document,
  which never edits the signed text.
- **The post-admission result record and the five-line report:** one comment on #540 (step 15) — the authoritative
  record. A local copy (`R10-W7-POST-ADMISSION.md`) is recovery evidence only.

### 5. END

- **The three remaining planned PRs**, as drafts (the readiness-fix PR, step 0, is merged: #624): the deployment files
  (step 1); the signed audit (step 10); the docs-only admission record (step 14) — plus any NEW admission-blocker fix PR §0.4 permits, under
  its rules. The owner reviews;
  each merges ONLY through `R10-merge-guard.py` (§0.0 control 1), and each body
  says: *"This PR is merged through the temporary R10 merge guard, extended through W7 only by the owner/consultant
  admission ruling of 2026-10-29, while native branch protection on `main` is unavailable."*
- **The five-line report** — closing the post-admission comment on #540 (step 15) and the window's final report:
  deployed where — the exact SHA and image digest; the SLO results (met, or the STOP); the audit signed by whom, with
  its governance exception; the tenant admitted; what remains behind the rail gate — and that native branch protection
  is still owed.
- **W7 is complete only when the #540 comment exists.** If it had to be handed to the delivery owner to post, the
  window ends reporting that it is NOT yet complete, and names the one act left: post it and confirm it on #540.
- **Memory:** add a newest dated entry to `memory/pricing-remodel-codebuilder-map.md`, and update
  `memory/ubb-not-deployed.md` — it is no longer true.
