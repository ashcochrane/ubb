SDK v5.0.0 RELEASE EVIDENCE - TAG + REPRODUCIBLE WHEEL - NOT PUBLISHED TO PYPI - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# PR body — "SDK v5 release record: pin the released wheel SHA-256" (saved with the release evidence)

**A post-release recording step, not a release.** `sdk-v5.0.0` was already created before this PR (2026-11-09, the
owner's separate release ruling): an annotated tag, object `fbf765b7efc19c2f3b08f2313ae6e72923e4b340`, which
dereferences to **`b41b395f59d798cec83289d83d5ec71f83201c7f`** — the `main` this PR branches from. The tag remains
immutable there; this PR does not create, move, delete or replace any tag.

The wheel was already canonically built and verified: the tag's own `ubb-sdk/release/build_wheel.py` (recipe
SHA-256 `f6bbb0d39dd6aeeffb8f423727f7bfd45eabbb427e8c7bde8da5944cea4831c7`) built
**`ubb_sdk-5.0.0-py3-none-any.whl`**, SHA-256
**`56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`**, twice from a clean export of the tag in the
hashed lock (`7bd4b746aa72c0852ecb5be1a171695ced7188e12c291e1e3fdd0f4b00ae9da0`) on Python 3.13.14 with
`SOURCE_DATE_EPOCH` 1794191690, one SHA-256 across both builds; it was then installed and verified in a fresh clean
environment (the SDK release tests and the whole SDK suite ran against the installed wheel), and its contents were
compared file by file with the tag's tree. The evidence package is `R10-SDK-V5-RELEASE/` (project folder; the
manifest `sdk-v5.0.0.release.json` and the wheel are retained there, never committed).

**This PR only records that completed release artefact in `ubb-sdk/CHANGELOG.md`**, in the 4.0.0 entry's
"Release stamp" table convention (which the SDK README says is where the released wheel's SHA-256 is recorded): the
tag, the exact tagged commit, the wheel filename, the complete 64-character SHA-256, the two-build reproduction, the
lock/recipe/epoch identities, and that it is delivered as a wheel and not published to PyPI. Every hash in the
record was read mechanically from the release manifest and a fresh hash of the retained wheel, and asserted equal.

- No wheel is rebuilt.
- No package is published (no PyPI, no index, no GitHub Release).
- No product behaviour changes: no code, test, migration, contract, generated artefact, version number, release
  tooling, README or MIGRATION change. `git diff --name-only` = `ubb-sdk/CHANGELOG.md`, exactly one file.
- W7 (`R10-W7-DELIVERY-PROMPT.md`) remains untouched, STATUS `PRE-LAUNCH — NOT FINAL`.
- `ubb-sdk/tests/test_release.py`: 23 passed in the repository venv against this tree; `git diff --check` clean;
  the forbidden-terms sweep green.
- **This PR is merged through the temporary R10 merge guard and by no other route.** State: `R10-merge-guard.py 633
  --check` has been run in check mode on exact head `1c347bd6efd147870fa340bc9c44377d09bbce7e` (the first run passed
  all five check families and refused only on this sentence's wording; the second run is the recorded check); the
  merging form has NOT been run and waits for the owner's separate explicit merge ruling. Never `gh pr merge`, never a
  direct push to `main`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
