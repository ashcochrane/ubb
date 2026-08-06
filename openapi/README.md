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

## Known-value metadata (#208, ADR-0008 §2)

The contract tells consumers which values UBB knows about, **without closing a
single open enum**. ADR-0003's open-enum stance is not reversed and not
weakened: an `open` concept keeps `type: string` and exposes its recognised
values as documentation metadata, because a schema that enumerated the set
would make UBB learning a new value a breaking change to a published contract.

A schema field says which registry concept it carries, and **only** that:

```python
class TaskOut(Schema):
    status: str = Field(json_schema_extra={"x-ubb-concept": "task_status"})
```

The values arrive at export time from `known-values.json` — generated from
`domain-vocabulary/` by `python -m tools.vocabulary --write`, and committed
beside this document. So the platform's source never spells a value set the
registry owns, and agreement is structural rather than a coincidence of
spelling (#191 decision 3).

| The concept's kind | What the exported document gets |
|---|---|
| `open` | `x-ubb-known-values`, beside an untouched `type: string`. Never an `enum`. |
| `closed` | a real `enum` — UBB owns the whole value set, so the schema may say so |
| `tenant_defined`, `free_text` | nothing, and a marker on one is **refused** |
| no `openapi` consumer in the registry | nothing, and a marker on one is **refused** |

`x-ubb-concept` survives into the published document. That is deliberate: it is
the concept-to-schema mapping G4 walks, and a mapping the gate had to infer by
comparing spellings would be one a coincidence could satisfy.

### The rule, and the order it forces

**The contract advertises a value only where the backend already serves it** —
asked through the consumer census (`tools/consumers`), which is G2 and G3's
predicate rather than a second copy of it. Emitting the final values on a field
that still returns the retired one would put a falsehood into a published
document, which is worse than saying nothing because a consumer can act on it.

So marking a field whose concept the backend does not yet serve **fails the
export**, naming the field. It is not silently skipped: the debt is already an
individually identified `G4` entry in `gates/migration-ledger.yaml`, and a
marker that quietly did nothing would be a check that cannot fail. The order is
therefore fixed, and it is one slice's single act:

1. convert the concept's backend consumer to import `core.vocabulary`;
2. regenerate — `python -m tools.vocabulary --write` flips it to advertised;
3. mark the schema field and regenerate the spec;
4. delete its ledger entry, and record any break with `--emit` below.

Today **no concept is served**, so this document carries no known-value
metadata and twenty-nine concepts are ledger entries. That is slice 0's correct
outcome: the mechanism is active and regressions are impossible, which is what
slice 0 is for.

## The three CI gates (`.github/workflows/ci.yml`, `contract` job)

1. **Drift gate** — regenerates offline and fails on any diff against the
   committed file. Also pinned in-suite by
   `api/v1/tests/test_openapi_contract.py`.
2. **Breaking gate** — `python openapi/contract_gate.py`, run from the git
   root. See "The cumulative breaking gate" below.
3. **TypeScript smoke gate** — the committed spec must generate clean TS
   types with a pinned `openapi-typescript`; nothing is committed on main
   (the revived UI branch owns real generation).

## The cumulative breaking gate

The gate does not ask "did this pull request break the contract?". It asks
**"has every break since the contract was published been reviewed?"** — so it
compares the spec at the immutable **`api-v1-launch`** tag against the working
tree, not against the base branch (#195, migration/cutover decision §7.3).

The difference is not academic. Comparing against the base branch proves only
that each step was reviewed *in isolation*, and a step that is never reviewed
is invisible forever after: #129's `contract` job went red on seven path
removals, the pull request was merged anyway, and no later per-pull-request
comparison could see them again. The cumulative comparison found them, and they
are now recorded in `oasdiff-err-ignore.txt`.

### The two comparisons

| | Command | Job |
|---|---|---|
| **The gate** (CI) | `python openapi/contract_gate.py` | validates the *complete* accepted break set — every cumulative break is proven reviewed |
| **Authoring** (you) | `python openapi/contract_gate.py --baseline origin/main --emit` | generates *your* new entries only, so a slice does not re-derive every earlier one |

`--emit` prints paste-ready lines, split by the file each belongs in. **Entries
are generated by running the tool and never hand-typed** — paste them verbatim,
then add your `#` comment block around them. Install the pinned oasdiff first
(the version is `OASDIFF_VERSION` in `contract_gate.py`; CI reads it from there,
so there is one pin, not two):

```
python openapi/contract_gate.py --print-pinned-version
# download that oasdiff release, put it on PATH, or point OASDIFF_BIN at it
```

The gate refuses to run against any other oasdiff version: findings are matched
by their reported text, so a different version can silently re-word every entry.

### What a cumulative comparison stops flagging

It measures divergence from the **published** contract, so a surface that was
added *after* the baseline and removed again before the next one never appears
as a break — the published contract never promised it. Per-pull-request
comparison did flag that case. The trade is deliberate (§7.3): churn inside the
re-model window is the **authoring** comparison's job, and the console typecheck
and SDK regeneration gates already fail on an in-repo consumer left behind.

### Two verdicts fail the gate

- **unreviewed** — a break no committed entry covers. Review it, then record it
  with `--emit`.
- **inert** — a committed entry that covers no finding *at its own level*.
  `--err-ignore` only ever suppresses ERR findings and `--warn-ignore` only WARN
  ones (oasdiff's `checker/ignore.go` filters by level before matching text), so
  a line in the wrong file silently does nothing. That has happened here: seven
  WARN-level lines sat in the ERR file suppressing nothing while two ERR
  findings went unrecorded. The same rule keeps human metadata on `#` comment
  lines, since prose that is not a generated finding matches nothing either. The
  well-formedness half is pinned in-suite by
  `api/v1/tests/test_contract_gate.py`.

The gate applies the two files itself — matching oasdiff's own rule (the line
must contain the operation, the path and the finding text, case-insensitively)
against `--format json` output — because oasdiff can suppress a finding but
cannot tell you that an entry suppressed nothing. The files keep oasdiff's
format either way, so a raw run still works and agrees:

```
oasdiff breaking --fail-on WARN \
  --severity-levels openapi/oasdiff-severity-levels.txt \
  --err-ignore openapi/oasdiff-err-ignore.txt \
  --warn-ignore openapi/oasdiff-warn-ignore.txt \
  <api-v1-launch spec> openapi/v1.json
```

### The suppression files cannot reach zero

Not a backlog. While the baseline is `api-v1-launch`, the differences from that
tag are real, intentional and permanent; the files **grow** as reviewed breaks
land. They clear only when slice 8 tags a **new** baseline and the gate is
pointed at it — `api-v1-launch` is never moved or deleted (§7.5).

This is the **opposite mechanism** from the implementation-rule migration
ledgers, which are seeded with today's known violations and must **shrink to
empty** by slice 8. Growing-and-intentional vs shrinking-and-defective — do not
conflate them.

So never delete an entry to make a suppression file shorter. Delete one only
when the gate reports it **inert**: it no longer describes a real break, and has
become a lie about what was reviewed.

### What may be added

Because the baseline *is* the launch tag, every entry is by construction a
post-launch break — which is why the old `LAUNCH TAG BOUNDARY` marker is gone,
along with the 20 pre-tag entries the tag already contains (they matched nothing
and the gate reported them inert; they remain in git history). A new entry is
permitted only:

- in the **pre-live lane** — no tenant is integrated against v1, so the break is
  hand-coordinated with the one known consumer.
  [`docs/api-compatibility.md`](../docs/api-compatibility.md) carries the dated
  note and names the day it is deleted; or
- as evidence of an **ADR-003 §4 deprecation already in flight** —
  `deprecated: true` on the operation, a runtime `Sunset` header (register the
  route in `ubb-platform/api/v1/deprecation.py`), a dated changelog entry +
  email announcement, and ≥90 days' notice (a floor we may raise, never lower).

From the first live tenant, only the second remains. A bare removal or rename is
a contract breach, not a CI escape hatch.

`oasdiff-severity-levels.txt` encodes the ADR-003 open-enum stance: a new
response-enum value is additive under our contract, whatever the tool default
says.
