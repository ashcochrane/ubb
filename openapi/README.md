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
     suppression files: accepting a break means adding a line here in the
     same PR — a visible, deliberate, reviewed change. (Pre-launch breaks
     ride this lane; after the launch tag, every entry requires the ADR-003
     deprecation process.) Lines are free-text matches against oasdiff's
     reported error text.
3. **TypeScript smoke gate** — the committed spec must generate clean TS
   types with a pinned `openapi-typescript`; nothing is committed on main
   (the revived UI branch owns real generation).
