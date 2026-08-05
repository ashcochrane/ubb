# The repository-wide contract suite

Checks that verify **agreement between** the platform, the console, the SDK and
the committed contract — rather than anything inside one of them.

They live at the git root because a check hosted by one party to an agreement
can only ever see its own side. The registry's validity, the zero-diff checks
over every generated artifact, the directly-validated hand-authored surfaces,
the forbidden-term sweep and the ledger and manifest checks all belong here.

## Running

From the git root:

```
python -m pytest tests/contracts
```

Two pinned packages, no Postgres, no Redis, no Django:

```
pip install -r tests/contracts/requirements.txt
```

That install list is the point, not an economy. This suite must run without
Django, and installing `ubb-platform/requirements.lock.txt` would make the claim
unfalsifiable — a Django import creeping into a contract test would simply work.
`test_contract_suite_is_enforced.py` asserts the CI job installs this file and
not that one.

## This suite gates (ADR-0008 §7)

*Test location predicts enforcement.* A must-pass invariant does not live under
an umbrella whose contract is informational, so everything here is required:
the `contracts` job in `.github/workflows/ci.yml` runs on every push and pull
request, with no `continue-on-error`, no `if:` and no path filter.

None of that is left as intention. `test_contract_suite_is_enforced.py` parses
the workflow and asserts it, with negative controls proving the predicate flags
a job that has been disarmed each way. Disarming this gate therefore means
deleting the test that says it is armed — a visible act in a diff, which is the
whole difference between this and the sweep that shipped `continue-on-error`.

The deliberate contrast is `ubb-platform/conformance/`: a stochastic, unseeded
schemathesis probe that is **not** promoted to a gate, is excluded from default
collection, and is `continue-on-error` on purpose. A reader can tell from where a
test lives whether its failure is a bug or a note.

## What a check here looks like

Three obligations, taken from `apps/platform/tests/test_product_boundaries.py`,
which is the house pattern:

1. **A negative control.** A synthetic violation, classified through the gate's
   real entry point, that must fail. A gate that has never been shown to fail is
   an assertion, not evidence.
2. **A vacuity guard.** Proof the gate actually read its subject — the registry
   check asserts the files it loaded are exactly the files on disk and names the
   concepts it must have seen. A gate that silently walks nothing is worse than
   no gate, because the board stays green.
3. **No mock of the thing under test.** Three SDK methods called routes that
   existed in no spec and no router and stayed green for months, because their
   tests patched the HTTP client and the mock reproduced the generator's mistake
   instead of contradicting it.

## Layout

| File | What it checks |
|---|---|
| `test_vocabulary_registry.py` | `domain-vocabulary/` is valid: the shipped registry, one negative control per named rejection reason, and the legal constructions that must keep passing. |
| `test_generated_vocabulary.py` | Every artifact generated from the registry is exactly what the registry produces, and the generated backend module *means* what the registry says — asserted by executing it, not by matching its text. |
| `test_gate_manifest.py` | `gates/manifest.yaml` is true: all twenty-seven of ADR-0008 §8's gates are accounted for, every `installed` row's check is proven to actually run and be able to fail, and every owed row names a real slice and what must exist first. |
| `test_migration_ledger.py` | The ledger only shrinks, every entry names an installed gate and an unlanded owner slice, and the permanent exceptions are a separate list with a different shape. |
| `test_model_naming_ledger_agreement.py` | The four model-naming gates (#203) excuse exactly the debts `gates/` records. Those gates run in the platform suite because their subject is the app registry, so the seeded sites exist twice — this holds the two encodings to each other, by id and in both directions. |
| `test_sdk_operations.py` | The SDK's two-way operation check (#204): every hand-written call targets a published operation by method **and** normalised path, and every published operation carries a derived disposition in a manifest that regenerates with zero diff. Carries #155 §8.5's six named cases, one test each. |
| `test_contract_suite_is_enforced.py` | This suite runs, is required, and needs no Django. |
| `_helpers.py` | Builds synthetic registries on disk for the negative controls, off the **real** schema — so a change to the shipped kind table is felt by every control. Also copies the **real** registry, for the controls that must mutate exactly one thing about it. |
| `_gate_helpers.py` | The same, for gate programmes: a synthetic `gates/`, workflow and test tree on disk, loaded through the real compiler. Also drives the ledger ratchet through a real git repository, because resolving a base ref is the one part a pure test cannot reach. |
| `_sdk_helpers.py` | The same, for SDK surfaces: a synthetic contract, hand shell, generated client and ledger on disk, read through the real walker. Path *expressions* rather than paths, so a control can express an f-string, a variable or a concatenation — the cases that are about how a route was written. |
| `conftest.py` | Puts the git root on `sys.path`. That is the entire fixture surface. |

The gate manifest is this slice's **single coordinating verdict**: the gates
themselves live in four places — here, the platform suite, the SDK suite and the
workflow — and `gates/manifest.yaml` is the one place all of them are accounted
for. `gates/README.md` carries the reasoning.
