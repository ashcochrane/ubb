PRE-ASH BILLING READINESS - FINAL TRANSITION WINDOW - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# R10 BILLING READINESS - FINAL TRANSITION WINDOW RECORD (2026-11-09 NZDT)

**Disposition: `R10 BILLING READINESS: INTERNAL PROGRAMME COMPLETE — HANDED FORWARD TO ASH`.**

Internal billing repair (Stage A, C1a-C5), verification/handoff (Stage B, Stage D, `R10-ASH-HANDOFF-2/`) and the SDK v5
release (tag, wheel, verification, repository record #633) are complete. Remaining work is the W7/external operational
lane (`R10-ASH-HANDOFF-2/05-WHAT-ASH-INHERITS.md`). This does NOT mean production-ready, W7 passed, a first customer
admitted, or a payment rail activated - none has happened.

## P0 - final state re-established before any edit (all held; no reconciliation was needed)

| Check | Result |
|---|---|
| `git fetch origin main --tags`; `origin/main` | `90d008b709a86ff0d63588d8dd6b0a160978230b` (exact) |
| Open PRs against `main` | none |
| Working repository | no tracked file modified (the 53 untracked paths are the long-standing research-branch files; branch `research/code-builder-prior-art`) |
| Remote `sdk-v5.0.0` | annotated tag, object `fbf765b7efc19c2f3b08f2313ae6e72923e4b340`, `^{}` = `b41b395f59d798cec83289d83d5ec71f83201c7f` (local `cat-file -t` = `tag`) |
| Retained wheel `R10-SDK-V5-RELEASE/ubb_sdk-5.0.0-py3-none-any.whl` | SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948` |
| PR #633 | MERGED, mergeCommit `90d008b7…`, head `1c347bd6…`, mergedAt 2026-11-09T03:55:58Z |
| `R10-ASH-HANDOFF-2/` | Stage D COMPLETE; SDK release COMPLETE; release record (#633) COMPLETE; BILLING BLOCKER 0; PRE-ASH REQUIRED FIX 0 |
| `R10-W7-DELIVERY-PROMPT.md` STATUS | `PRE-LAUNCH — NOT FINAL` (SHA-256 before `4f737176dc6cd517c3746f59242822bd7393293b13aba0f3c967512c8877f147`) |
| `api-v1-cutover^{}`, `sdk-v4.0.0^{}` | both `c2eb35ff…` (unmoved) |

## 1. W7 anchor - POINTER ONLY (W7 NOT executed)

Before: `Refreshed at main = a674e9d0 (2026-11-02, …)`; P0(g) expected `origin/main` = `a674e9d0a2430601a4e5350d55c59e6221daa147`.
After: `Refreshed at main = 90d008b7 (2026-11-09, the FINAL TRANSITION WINDOW …)`; P0(g) expects `origin/main` =
`90d008b709a86ff0d63588d8dd6b0a160978230b` (sole parent `b41b395f…` = #632; its sole parent `a6738e78…` = #631, the
Stage D behavioural proof anchor). STATUS unchanged: `PRE-LAUNCH — NOT FINAL`. The seven launch inputs stay blank.
One factual note added under §0.5 step 13: `sdk-v5.0.0` exists and `main` publishes the v5 contract; which SDK major
the first client is handed is a W7 policy matter left to the owner's final factual review (NOT changed here).
W7 prompt SHA-256 after: `aedcb0d05814ae5871dde89ffb47763140fc3f141fe1fec23e29fb11a721edce`. Full diff below.

## 2-4. HANDOFF-2 edits (evidence only)

- `00-README.md`: the three-identities table (D1 proof anchor / SDK release commit / current baseline, with the
  statement that #632 and #633 were documentation/release-record only and changed no billing behaviour; the D1 proof is
  NOT relabelled); file table gains `START-HERE-ASH.md`; the "next owner sequence" marks the W7 refresh and the Ash
  transfer DONE; the closing record and disposition appended.
- `03-ASH-VALIDATION-AND-NEXT-STEPS.md`: the #633 successor and current `main` added; "the owner refreshes" wording
  replaced with DONE wording; the "do not run yet" list no longer names the W7 anchor refresh as pending.
- `05-WHAT-ASH-INHERITS.md`: identity line; new §0 "Completed before handoff - NOT Ash's work"; §6 and §9 closing
  sentences updated.
- `START-HERE-ASH.md`: created (reading order; exact identities; what was proved; what was NOT proved; what Ash does next).
- `01`, `02`, `04`: unchanged (all anchored to `a6738e78…`, still true).

## 6. Hygiene and immutability (run 2, final)

    == secret-shaped value scan
      files scanned: 22; secret-shaped values: 0 (documented placeholders exempted: 19)
    == required-header check (.md and .txt first line)
      files without the required header: 0
    == immutable packages re-check against the pre-window SHA-256 manifests
      R10-ASH-HANDOFF: manifest 4 files, now 4 files, changed_or_missing=0
      R10-BILLING-READINESS: manifest 98 files, now 98 files, changed_or_missing=0
    == W7 prompt
      STATUS line begins with PRE-LAUNCH, em dash, NOT FINAL: True (1 STATUS line(s))
      SHA-256 before: 4f737176dc6cd517c3746f59242822bd7393293b13aba0f3c967512c8877f147
      SHA-256 after : aedcb0d05814ae5871dde89ffb47763140fc3f141fe1fec23e29fb11a721edce
    HYGIENE: CLEAN

Run 1 flagged three classes, all documented non-secrets, exempted in run 2: `SECRET_KEY=local-throwaway` (a literal
placeholder in `03`'s local recipe); truncated `whsec_localp...` echoes of the exempt `whsec_localpass_a/b/c`
placeholders inside `R10-SDK-V5-RELEASE/evidence/07-final-state-and-hygiene.txt`; and two `.txt` banners behind a UTF-8
BOM. No credential or secret value appears in either package. `R10-ASH-HANDOFF/` (4 files) and `R10-BILLING-READINESS/`
(98 files) are byte-identical to their pre-window manifests.

## 7. No repository implementation

No product code or repository file changed; no PR, no commit, no push; `sdk-v5.0.0` not moved; no wheel rebuilt; no
deployment, rail activation, production credential, W7 execution or tenant admission. Every edit above is a
project-folder evidence/prompt file.

## Appendix - W7 prompt diff (before -> after)

```diff
--- w7-before.md	2026-11-09 17:16:52.089149800 +1300
+++ /c/Users/tom_l/.claude/projects/C--Users-tom-l-git-ubb/R10-W7-DELIVERY-PROMPT.md	2026-11-09 17:16:52.313243600 +1300
@@ -1,6 +1,22 @@
 # R10-W7 — Delivery close-out: deploy, measure, audit, admit
 
-> **STATUS: PRE-LAUNCH — NOT FINAL.** Refreshed at `main` = `a674e9d0` (2026-11-02, later: the pre-Ash billing
+> **STATUS: PRE-LAUNCH — NOT FINAL.** Refreshed at `main` = `90d008b7` (2026-11-09, the FINAL TRANSITION WINDOW of the
+> pre-Ash billing-readiness programme — a baseline-pointer refresh only; W7 was NOT executed. The W7 starting repository
+> baseline is now `90d008b709a86ff0d63588d8dd6b0a160978230b`, the squash of the docs-only SDK release-record PR #633; its sole
+> parent is `b41b395f59d798cec83289d83d5ec71f83201c7f` (the squash of the docs-only Stage D D2 PR #632), whose sole parent is
+> `a6738e78e96ab10eabd45dc10fafdc842b7de519` (the squash of Stage C5 PR #631) — the Stage D behavioural proof anchor, on which
+> every billing golden path was re-proven with zero BILLING BLOCKER and zero PRE-ASH REQUIRED FIX (`R10-ASH-HANDOFF-2/`).
+> The two successors after that anchor are documentation/release-record changes only and changed no billing behaviour.
+> Also since the previous refresh: billing-readiness Stage C1a–C5 (#626–#631) merged through the temporary R10 merge
+> guard, and `sdk-v5.0.0` was released — an annotated tag dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`, wheel
+> `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`,
+> `R10-SDK-V5-RELEASE/`, not published to PyPI (see the factual note under §0.5 step 13). None of this is W7 admission
+> evidence. The temporary R10/W7 merge guard was a compensating control for those merges, not branch protection; native
+> required-check enforcement on `main` remains the accepted temporary governance limitation (§0.0) until the repository
+> owner applies the ruleset. W7 has NOT been executed: no deployment, hosting, SLO measurement, production credential,
+> rail activation or real-client admission has occurred because this anchor moved; `api-v1-cutover^{}` still `c2eb35ff`;
+> the seven launch inputs still blank. The internal billing-readiness programme is closed and handed forward to Ash
+> (`R10-ASH-HANDOFF-2/START-HERE-ASH.md`). Before that at `main` = `a674e9d0` (2026-11-02, later: the pre-Ash billing
 > readiness Stage A PR #625 — the wallet-subject mutation perimeter — merged through the guard at reviewed head
 > `f8539dd7` under the Stage-A-only authorisation, squash `a674e9d0a2430601a4e5350d55c59e6221daa147`, record
 > `R10-BILLING-STAGE-A-MERGE.md`; it is not W7 admission evidence; `api-v1-cutover^{}` still `c2eb35ff`; the seven
@@ -205,12 +221,14 @@
       2026-11-02 through the guard) - `git merge-base --is-ancestor 1bf0c0ca origin/main` holds, #624 reads MERGED,
       and the readiness evidence (R10-W7-PREP/readiness/) is read. Do NOT implement F1/F2/F3/F5/F6 again. If any
       of that is false, STOP.
-  (g) THE EXPECTED BASELINE IS THE POST-STAGE-A MAIN: origin/main equals exactly
-      a674e9d0a2430601a4e5350d55c59e6221daa147 (the squash of billing-readiness Stage A PR #625 at reviewed head
-      f8539dd7, merged 2026-11-02 through the guard under the Stage-A-only authorisation; record
-      R10-BILLING-STAGE-A-MERGE.md), #625 reads MERGED, and `git merge-base --is-ancestor a674e9d0 origin/main`
-      holds. If origin/main has moved past it, STOP and report the SHA (the owner refreshes this line; a later
-      Stage C merge is the one expected mover). Stage A is not admission evidence and authorised nothing here.
+  (g) THE EXPECTED BASELINE IS THE FINAL POST-PROGRAMME MAIN: origin/main equals exactly
+      90d008b709a86ff0d63588d8dd6b0a160978230b (the squash of the docs-only SDK release-record PR #633, merged
+      2026-11-09 through the guard; sole parent b41b395f59d798cec83289d83d5ec71f83201c7f = the docs-only Stage D D2
+      squash #632; its sole parent a6738e78e96ab10eabd45dc10fafdc842b7de519 = the Stage C5 squash #631 and the Stage D
+      behavioural proof anchor; records R10-BILLING-STAGE-D-MERGE.md and R10-SDK-V5-RELEASE/00-README.md), #625-#633
+      read MERGED, and `git merge-base --is-ancestor a674e9d0 origin/main` and `... a6738e78 origin/main` both hold.
+      If origin/main has moved past it, STOP and report the SHA (the owner refreshes this line; no further pre-W7
+      mover is expected). Stage A-D and the sdk-v5.0.0 release are not admission evidence and authorised nothing here.
 
 Must not miss:
   0. STEP 0 (sec 0.5, sec 0.6) IS DONE PRE-FINAL - verify it per P0(f); never re-implement it. Never record, build
@@ -501,6 +519,12 @@
     the #561 usage-summary proof. A health check or a database row alone is not client acceptance.
 13. Hand the client the exact `sdk-v4.0.0` wheel, `ubb_sdk-4.0.0-py3-none-any.whl`, with its SHA-256
     `fdf9ae7688a9e5c632f83fb64347abc65de3e2f1db943b69f08edcb12ddf4d89` (`R10-W6-RELEASE/`).
+    *(Factual note, 2026-11-09, final transition window — a fact refresh, NOT a policy change: `sdk-v5.0.0` has since
+    been released — annotated tag dereferencing to `b41b395f59d798cec83289d83d5ec71f83201c7f`, wheel `ubb_sdk-5.0.0-py3-none-any.whl`,
+    SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`, `R10-SDK-V5-RELEASE/`, not published to PyPI — and
+    `main` now publishes the v5 contract (Stage C5, #631, the one deliberate post-cutover breaking regeneration; SDK 4.x
+    does not match it). Which SDK major the first client is handed, and therefore the SDK named by the P2 path above,
+    is a W7 policy matter for the owner's final factual review; this refresh deliberately leaves it unchanged.)*
 14. **Once steps 11–13 have succeeded**, merge one tiny **docs-only admission-record PR** through the W7 merge guard:
     it deletes the dated pre-admission note from `docs/api-compatibility.md` (`:10`, the *"Status, as of 2026-07-28"*
     block) — that deletion is the repository's admission record (ADR-0007 §5), made only after admission actually
```

---

## ADDENDUM - FINAL OWNER/CONSULTANT RULING (2026-11-09, after the review of this record)

The earlier before/after evidence above is left as written. The one policy point it flagged is now CLOSED.

**Ruling:** the first client MUST receive SDK v5.0.0 if it integrates through the Python SDK. This supersedes the older
W7/R2 instruction to hand the first client SDK v4, because current `main` publishes the v5 contract (Stage C5's one
deliberate pre-live breaking regeneration), SDK 4.x does not match it, and `sdk-v5.0.0` is released, reproducibly built
and independently verified.

| Item | Value |
|---|---|
| Tag / release commit | `sdk-v5.0.0` → `b41b395f59d798cec83289d83d5ec71f83201c7f` |
| Wheel | `ubb_sdk-5.0.0-py3-none-any.whl` |
| SHA-256 | `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948` |
| Evidence | `R10-SDK-V5-RELEASE/` (handed over by file; not published to PyPI) |

**Operative W7 updates (`R10-W7-DELIVERY-PROMPT.md`; STATUS untouched, W7 not executed):**

- STATUS paragraph: the "see the factual note" pointer replaced by the ruling sentence.
- Final factual-review binding (§ "The final factual review"): `P2 if the client integrates through SDK v5`.
- Launcher "Must not miss" execution summary: `P2 if SDK v5`.
- §0.5 step 12: `P2 if the client integrates through SDK v5`.
- §0.5 step 13: the v4 handoff instruction and the temporary "which SDK major" policy note REPLACED by the ruled
  instruction: hand the client `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256 `56d28b90…` (`R10-SDK-V5-RELEASE/`), the
  released SDK matching the current v5 contract, handed over by file, not on PyPI.
- "Client golden path - CLIENT GOLDEN PATH READY accepted": `P2 if SDK v5 (RULED 2026-11-09)`.
- Historical R2 quotation (§2 "What binds this window"): PRESERVED verbatim; immediately followed by
  "SUPERSEDED FOR FIRST-CLIENT SDK HANDOFF by the FINAL owner/consultant ruling of 2026-11-09: use `sdk-v5.0.0` and its
  verified wheel … The remaining R2 defaults continue to stand unless separately superseded."
- P1/P2/P3 meanings otherwise unchanged. No other v4 wording remains operative (`grep` shows only the R2 quotation and
  the step-13 "supersedes … SDK v4" sentence).

**HANDOFF-2:** `START-HERE-ASH.md` now states "If the first client integrates through the Python SDK, W7 hands it
`sdk-v5.0.0`, using the verified wheel in `R10-SDK-V5-RELEASE/`" and carries the policy-closure line; the "open owner
policy point" sentence is removed. `05` §0 lists the ruling among the completed, not-inherited items. `00-README.md`'s
closing record carries the ruling and the closure line. File `03`'s first "Where the programme is now" bullet now reads
"The D1 behavioural proof anchor is `a6738e78…` (at D1, `main` was `a6738e78…`)"; the D2 → `b41b395f…`, SDK release and
#633 → `90d008b7…` statements are retained; D1 is not relabelled.

**W7 prompt SHA-256 after these final edits: `a66f229028be96046d2308a26c85f4d200a349e4ddf88bb6c21b057283ea3c6c`**
(was `4f737176…` before the window, `aedcb0d0…` after the anchor refresh).

**Final hygiene / consistency (run 3):**

    == secret-shaped value scan
      files scanned: 22; secret-shaped values: 0 (documented placeholders exempted: 19)
    == required-header check (.md and .txt first line)
      files without the required header: 0
    == immutable packages re-check against the pre-window SHA-256 manifests
      R10-ASH-HANDOFF: manifest 4 files, now 4 files, changed_or_missing=0
      R10-BILLING-READINESS: manifest 98 files, now 98 files, changed_or_missing=0
    == W7 prompt
      STATUS line begins with PRE-LAUNCH, em dash, NOT FINAL: True (1 STATUS line(s))
      SHA-256 before: 4f737176dc6cd517c3746f59242822bd7393293b13aba0f3c967512c8877f147
      SHA-256 after : a66f229028be96046d2308a26c85f4d200a349e4ddf88bb6c21b057283ea3c6c
    HYGIENE: CLEAN

Repository re-check after the edits: `origin/main` = `90d008b709a86ff0d63588d8dd6b0a160978230b`; no open PR against
`main`; no tracked file modified; `sdk-v5.0.0` object `fbf765b7…` → `b41b395f59d798cec83289d83d5ec71f83201c7f`; wheel
SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`; W7 STATUS `PRE-LAUNCH — NOT FINAL`; launch
inputs blank 7/7; W7 not executed; no deployment, rail activation, production credential, product change or PR.

**FINAL DISPOSITION:**

`R10 BILLING READINESS: INTERNAL PROGRAMME COMPLETE — HANDED FORWARD TO ASH`

`FINAL OWNER POLICY CLOSURE: first-client Python SDK = sdk-v5.0.0.`

There are NO unresolved internal owner decisions in the pre-Ash billing-readiness handoff. The remaining decisions are
the W7 launch inputs and operational decisions, by design. No further internal engineering or readiness work follows.
