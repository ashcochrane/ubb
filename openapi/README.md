# The committed OpenAPI contract

`v1.json` is the single source of truth for the tenant-facing API surface
(ADR-002). It is **generator-owned — hand edits are refused** by CI's drift
gate. The document also carries the OpenAPI 3.1 `webhooks` section: the full
outbound event catalog with frozen payload schemas.

## Regenerating

After any surface change, from `ubb-platform/`:

```
python scripts/export_openapi.py
```

Output is deterministic (sorted keys, LF, trailing newline), so the diff you
commit is exactly the surface change you made — the spec diff is the API
review.

## The three CI gates (`.github/workflows/ci.yml`, `contract` job)

1. **Drift gate** — regenerates offline and fails on any diff against the
   committed file. Also pinned in-suite by
   `api/v1/tests/test_openapi_contract.py`.
2. **Breaking gate** — `oasdiff breaking` (pinned version) against the base
   branch's committed spec, failing on warnings and errors.
   - `oasdiff-severity-levels.txt` encodes the ADR-003 open-enum stance:
     a new response-enum value is additive under our contract, whatever the
     tool default says.
   - `oasdiff-err-ignore.txt` / `oasdiff-warn-ignore.txt` are the committed
     suppression files: `--err-ignore` suppresses ONLY ERR-level findings and
     `--warn-ignore` ONLY WARN-level findings (oasdiff's `checker/ignore.go`
     filters by level before matching text) — a WARN-level line dropped into
     the err-ignore file (or vice versa) silently suppresses nothing, so file
     a finding by the level oasdiff actually reports it at, not by which file
     is more convenient. Accepting a break means adding a line here in the
     same PR — a visible, deliberate, reviewed change. Lines are free-text
     matches against oasdiff's reported error text. **Don't hand-derive these
     entries** — install the pinned `OASDIFF_VERSION` binary
     (`.github/workflows/ci.yml`) and run `oasdiff breaking` against the base
     spec locally, then paste its reported text verbatim.
     - **Both files** carry a **`LAUNCH TAG BOUNDARY`** marker (err-ignore
       since #86; warn-ignore since the 2026-07-27 unified-dimension-model
       final-fixes wave). Every entry **above** it is a pre-launch free break,
       hand-coordinated with the one known tenant. From the launch tag onward,
       a **new** entry **below** the marker is permitted **only as evidence of
       an ADR-003 §4 deprecation already in flight** — `deprecated: true` on
       the operation, a runtime `Sunset` header (register the route in
       `ubb-platform/api/v1/deprecation.py`), a changelog + email, and ≥90
       days' notice. A bare removal or rename below the marker is a contract
       breach, not a CI escape hatch. The customer-facing promise is
       [`docs/api-compatibility.md`](../docs/api-compatibility.md).
3. **TypeScript smoke gate** — the committed spec must generate clean TS
   types with a pinned `openapi-typescript`; nothing is committed on main
   (the revived UI branch owns real generation).
