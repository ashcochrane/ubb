SDK v5.0.0 RELEASE EVIDENCE - TAG + REPRODUCIBLE WHEEL - NOT PUBLISHED TO PYPI - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# R10 - the `sdk-v5.0.0` release act (2026-11-09, job 2895592e)

The owner's separate release ruling after Stage D: cut `sdk-v5.0.0` on the exact post-D2 `main`, build the wheel
through the repository's canonical release recipe, verify the wheel independently, record it here, and tell
`R10-ASH-HANDOFF-2/` that the act is complete. Nothing was published to PyPI or any index. `main` did not move.
W7 (`R10-W7-DELIVERY-PROMPT.md`) was not touched and its STATUS stays `PRE-LAUNCH - NOT FINAL`. No product or
repository code changed; no PR was opened. The only write to the remote was the one tag ref.

## Release identity

| Item | Value |
|---|---|
| Authoritative `origin/main` (before, during and after) | `b41b395f59d798cec83289d83d5ec71f83201c7f` ("Stage D docs: the SDK README, the codegen README and the glossaries say what main does (#632)"; sole parent `a6738e78e96ab10eabd45dc10fafdc842b7de519`, the D1 behavioral anchor) |
| Tag | `sdk-v5.0.0` |
| Tag object type | `tag` (annotated; unsigned, as `sdk-v4.0.0` is) |
| Tag object SHA | `fbf765b7efc19c2f3b08f2313ae6e72923e4b340` |
| Dereferenced commit (`sdk-v5.0.0^{commit}`) | `b41b395f59d798cec83289d83d5ec71f83201c7f` |
| Tag message | `ubb-sdk 5.0.0, the one deliberate major after the cutover (R10 billing readiness Stage C5, #631; ADR-0026)` |
| Tagger | the repository owner's git identity, 2026-11-09 16:03:07 +1300 |
| Push | `git push origin refs/tags/sdk-v5.0.0:refs/tags/sdk-v5.0.0` - the tag ref only; no branch, no commit |
| Remote proof | `git ls-remote --tags origin`: `refs/tags/sdk-v5.0.0` = `fbf765b7…`, `refs/tags/sdk-v5.0.0^{}` = `b41b395f…`; `sdk-v4.0.0^{}` and `api-v1-cutover^{}` still `c2eb35ff…`, `api-v1-launch^{}` still `ac6ca816…` |
| Tagged commit reachable from `origin/main` | yes (`git merge-base --is-ancestor`) |

## The canonical build

| Item | Value |
|---|---|
| Recipe | the TAG's own `ubb-sdk/release/build_wheel.py`, SHA-256 `f6bbb0d39dd6aeeffb8f423727f7bfd45eabbb427e8c7bde8da5944cea4831c7` (unchanged since the v4 cut), run from a clean detached worktree at `b41b395f…` (status empty) |
| Command | `python3.13 ubb-sdk/release/build_wheel.py --tag sdk-v5.0.0 --commit b41b395f59d798cec83289d83d5ec71f83201c7f --out <this folder>` |
| Release Python | 3.13.14 (`Windows-11-10.0.26200-SP0`); installer pip 26.1.2 outside the build environment |
| Lock | `ubb-sdk/release/build-requirements.txt`, SHA-256 `7bd4b746aa72c0852ecb5be1a171695ced7188e12c291e1e3fdd0f4b00ae9da0`; installed exactly `build 1.2.2.post1`, `colorama 0.4.6`, `packaging 25.0`, `pyproject-hooks 1.2.0`, `setuptools 80.9.0`, no installer |
| `SOURCE_DATE_EPOCH` | `1794191690` (the tagged commit's committer time, 2026-11-09T02:34:50Z) - every zip entry in the wheel carries that one timestamp |
| Reproducibility | two builds in two fresh directories, one SHA-256 (`builds_compared: 2`); the recipe refused nothing; exit 0 in 1 m 18 s |
| **Wheel** | **`ubb_sdk-5.0.0-py3-none-any.whl`** (795,683 bytes), in this folder |
| **Wheel SHA-256** | **`56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`** |
| Release manifest | `sdk-v5.0.0.release.json` (this folder, written by the recipe; SHA-256 `bbf69c7a8b63c13e10a4ccd96e62c05f60d6ea05ee8a910b0206590f0945da8d`) |
| Embedded stamps | `ubb.__version__` `5.0.0`; `ubb.__spec_revision__` `1bf1af2350f22f0ad0c2652fd82e8b9cc028f41e879c29e833329740547e9a40` = SHA-256 of `openapi/v1.json` at the tag; `ubb.__spec_version__` `v1`; generator `openapi-python-client 0.29.0` |

## Independent verification

| Check | Result | Evidence |
|---|---|---|
| Wheel contents vs the tag's tree | every one of the 650 files under `ubb/` in the wheel has the git blob id of the tag's `ubb-sdk/ubb/` blob (650/650; nothing missing, nothing extra); METADATA `Name: ubb-sdk`, `Version: 5.0.0` | `evidence/03-wheel-vs-tag-tree.txt` |
| Clean-wheel install | fresh `python3.13 -I -s -m venv` (pip only), `pip install <wheel file>` (dependencies downloaded from PyPI; nothing uploaded); from a neutral directory in isolated mode: `ubb.__file__` in the venv's site-packages, `ubb.__version__ == "5.0.0"`, `importlib.metadata.version("ubb-sdk") == "5.0.0"`, pip's `direct_url.json` names the wheel file and its SHA-256 `56d28b90…`, all 656 RECORD entries re-hash clean on disk, `UBBClient` constructs | `evidence/04-clean-wheel-verification.txt` |
| Release tests against the installed wheel | `ubb-sdk/tests/test_release.py`: **23 passed**; the whole `ubb-sdk/tests` suite: **477 passed, 63 subtests passed**, 2 PyJWT key-length warnings (test fixture keys) - `ubb` imported from the wheel's site-packages before pytest started and confirmed unchanged after | `evidence/05-release-tests-against-wheel.txt` |
| Release evidence verifier | `tools/verify_sdk_v5_release.py` (project folder; adapted from the v4 `verify_w6_release.py`): 31 checks, **RELEASE EVIDENCE VALID**, exit 0 | `evidence/06-release-evidence-verifier.txt` |
| Final state | `origin/main` unchanged; W7 prompt byte-identical; main checkout and release worktree untouched; hygiene clean | `evidence/07-final-state-and-hygiene.txt` |

## What this release is not

- **Not published.** No `twine`, `pip upload`, GitHub Release or any index was used. The wheel is handed over as a
  release artefact in this folder (never committed to the repository, as 4.0.0's was not).
- **Not a repository change.** No file in the repository changed; no PR; `main` is `b41b395f…` throughout.
- **Not W7.** `R10-W7-DELIVERY-PROMPT.md` untouched (SHA-256 `4f737176dc6cd517c3746f59242822bd7393293b13aba0f3c967512c8877f147`
  before and after); STATUS `PRE-LAUNCH - NOT FINAL`; its anchor refresh to `b41b395f…` remains the owner's next
  separately authorised step.
- **Not a deployment, rail activation, or use of any production credential.**

## The post-release repository record — DONE (PR #633, merged 2026-11-09)

The 4.0.0 CHANGELOG stamp table carries a "Wheel and its SHA-256" row; the 5.0.0 entry had none at the release.
After the owner/consultant ACCEPTED the release, they ruled one documentation-truth item, done as a separate
post-release recording step (not a release):

| Item | Value |
|---|---|
| Change | `ubb-sdk/CHANGELOG.md` only: the 5.0.0 "Release stamp" becomes the 4.0.0-style table with the "Wheel and its SHA-256" row (tag, exact commit, wheel filename, full 64-character SHA-256, two builds one hash, lock/recipe/epoch, delivered as a wheel, not published to PyPI); every hash read mechanically from `sdk-v5.0.0.release.json` and a fresh hash of the retained wheel (`evidence/08-…`) |
| PR | **#633** "SDK v5 release record: pin the released wheel SHA-256"; reviewed head `1c347bd6efd147870fa340bc9c44377d09bbce7e` (parent `b41b395f…`); exact-head CI 12/12 success on both workflow runs; `R10-merge-guard.py 633 --check` run 1 refused only on the body marker wording, body corrected without changing the head, run 2 exit 0 (`evidence/09-…`) |
| Guarded merge | `python R10-merge-guard.py 633`, merge mode, run exactly once, exit 0: "MERGED #633 (squash) at head 1c347bd6…" (`evidence/10-guard-merge.txt`); no `gh pr merge`, no direct push |
| **Resulting `main`** | **`90d008b709a86ff0d63588d8dd6b0a160978230b`** ("docs(sdk): record the released sdk-v5.0.0 wheel SHA-256 in the CHANGELOG (#633)"), `mergedAt` 2026-11-09T03:55:58Z |
| Sole parent / no intervening commit | parent exactly `b41b395f59d798cec83289d83d5ec71f83201c7f`; `rev-list --count b41b395f..origin/main` = 1; `git log --oneline` shows only the #633 squash |
| Reviewed tree = merged tree | `e453d89ef755c803f005527eb2df0cc1585e6fb0` = `e453d89ef755c803f005527eb2df0cc1585e6fb0`; `git diff --stat 1c347bd6 origin/main` empty |
| Paths changed base → main | exactly `ubb-sdk/CHANGELOG.md` |
| Release identity after the merge | unchanged: `sdk-v5.0.0` object `fbf765b7…`, `^{}` `b41b395f…` (the tag was NOT moved to the docs commit); retained wheel still `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`; no new wheel; nothing published |

The SDK release and its repository release record are now BOTH complete. `b41b395f…` remains the release commit;
`90d008b7…` is the documentation-only successor that records it.

## Files

| Path | What |
|---|---|
| `ubb_sdk-5.0.0-py3-none-any.whl` | the release artefact |
| `sdk-v5.0.0.release.json` | the recipe's release manifest |
| `evidence/00-p0-identity.txt` | P0: fetch, `origin/main`, clean worktree, no open PR, no `sdk-v5.0.0`, every 5.0.0 declaration, tooling hashes, the release Python |
| `evidence/01-tag-create-and-push.txt` | tag creation, `cat-file -t/-p`, dereference, the tag-only push, remote listing after, `origin/main` after |
| `evidence/02-canonical-build.txt` | the recipe run, its printed manifest, timing, output listing, independent hashes |
| `evidence/03-wheel-vs-tag-tree.txt` | wheel contents vs the tag's blobs, METADATA, stamps, zip timestamps |
| `evidence/04-clean-wheel-verification.txt` | the fresh venv, the install, the isolated-mode probe |
| `evidence/05-release-tests-against-wheel.txt` | `test_release.py` and the whole SDK suite against the installed wheel |
| `evidence/06-release-evidence-verifier.txt` | `tools/verify_sdk_v5_release.py` output |
| `evidence/07-final-state-and-hygiene.txt` | end-of-window identity re-check and the hygiene pass over this folder and `R10-ASH-HANDOFF-2/` |

Related: `R10-W6-RELEASE/` (the 4.0.0 release, same recipe), `R10-BILLING-STAGE-D-MERGE.md`, `R10-ASH-HANDOFF-2/`.
