# The gate manifest and the migration ledger

Two bookkeeping artifacts that make the re-model's eight remaining slices
auditable, and one CI verdict that makes a gate impossible to lose (#201, under
slice 0 — #191).

| File | What it holds |
|---|---|
| `manifest.yaml` | One row per gate in ADR-0008 §8, plus the obligations that are not gates. Declares the pytest suites a row may name. |
| `slices.yaml` | The build programme's slices (#194) as data — the issue, the position in the dependency chain, and whether it has landed. |
| `migration-ledger.yaml` | Every current violation of an **installed** gate, individually identified, each owed by a named slice. Only ever shrinks. |
| `permanent-exceptions.yaml` | Deliberate exceptions with stated reasons. **Not** the ledger, and the reason for that is below. |
| `schema.yaml` | The shape rules the compiler enforces. Data, not documentation. |

Everything here is read by `tools/gates` and checked by
`tests/contracts/test_gate_manifest.py` and
`tests/contracts/test_migration_ledger.py`.

```
python -m tools.gates            # is every claim in the manifest true?
python -m tools.gates ratchet    # does the ledger owe more than the base branch's did?
```

## Why a manifest at all

ADR-0008 §8 lists twenty-seven standing gates in a table inside a frozen decision
document. A table is a list of intentions: nothing compares it against the
repository, and a gate that quietly stopped running would go on being listed as
one.

That is not hypothetical here. The repository has shipped the same failure three
times — **a check that exists but cannot fail anything**:

- the schemathesis sweep wired `continue-on-error: true`, so its findings can
  never turn a pull request red;
- the only end-to-end money test sat in no CI job at all and was dead for six
  months, still calling a retired endpoint;
- three SDK methods called routes existing in no spec and no router, green for
  months, because their tests patched the HTTP client.

To which #158 §16 adds a fourth shape not yet suffered: a path filter on a job
that never mentions a seventh input, which stops the gate running while the
board stays green — the same failure as `.gitignore`'s unanchored `lib/`
dropping twenty-two modules for weeks.

So a row claiming `installed` names where it runs, and every site is verified:

- the workflow runs on **both** push and pull request, with no `paths` or
  `paths-ignore` filter;
- neither the job nor the step is `continue-on-error` or conditional on `if:`;
- a named test node is one its suite **actually collects** — the file matches
  `python_files`, no `norecursedirs` or `--ignore` excludes it, the function
  exists and matches `python_functions`, and it carries no skip or xfail marker.

**This is the slice's single coordinating verdict.** The gates themselves live in
four different places — the contract suite, the platform suite, the SDK suite and
the workflow — and that is correct; a check belongs beside what it verifies.
What the manifest supplies is the thing distribution costs you: one place where
every gate is accounted for. Locations may vary; accountability may not.

## The three statuses

| Status | Means |
|---|---|
| `installed` | The check runs, is not skipped, and is not `continue-on-error`. `enforced_by` says where. |
| `owned_by_slice_N` | The subject does not exist yet. The named slice installs it, and `blocked_on` states what must exist first. |
| `deferred_obligation` | Not a CI check at all. Carries its reason, its owner role and the evidence required. |

`owned_by_slice_N` is not a listed status — it is derived, one per slice in
`slices.yaml`. So "every `owned_by_slice_N` names a real slice" is true by
construction rather than by a second check somebody has to remember to write.

**A gate whose subject does not exist is recorded against its owner, never
installed as a test that passes on nothing.** Three rows say so today: the four
`kind` discriminator pins have no column to pin (slice 5), no field is declared
into a transition class yet (slice 3), and ADR-0007 §1 states the data-carrying
migration rule does not bind before the cutover squash (slice 8).

### Flipping a row

The slice that installs a gate flips its own row, in the pull request that
installs it:

1. change `status` from `owned_by_slice_N` to `installed`;
2. delete `blocked_on` and add `enforced_by`, naming the suite node or workflow
   step;
3. add any violations the new gate finds to `migration-ledger.yaml`, with a
   seeding authorisation (below);
4. run `python -m tools.gates` — it will tell you if the site is not armed.

**And when the slice itself lands, set its `landed: true` in `slices.yaml`.**
That is what arms rule 3 below; until it is set, an entry owed by a finished
slice sits there looking owned. See the closing section for why this is declared
rather than observed.

A slice that lands while still named by an `owned_by_slice_N` row turns CI red:
a landed slice cannot owe an installation.

## The ledger, and its three rules

Every current violation of an installed gate, as an **individually identified
entry** carrying the gate, the exact site, the canonical term expected, the owner
slice that removes it, and a one-line reason.

1. **It only shrinks.** CI compares against the base branch's ledger and fails on
   any added entry — the same ratchet shape as the spec drift gate and the SDK
   regeneration gates. An entry may be added only through an explicit, reviewed
   override.
2. **Every entry names a real gate and a real slice**, and the gate must be
   `installed`. A debt recorded against a check that cannot fail anything is a
   note nothing will ever prove, clear or notice.
3. **An entry whose owner slice has already landed fails CI.** This closes #155
   §17's recorded residue — that the seeded allowlists had no stated owner per
   entry, so an entry could survive to slice 8 by everyone assuming somebody
   else owned it.

Two further rules follow from rule 1 rather than sitting beside it. An entry's
**identity is its gate and its site**, not its label — re-labelling is neither a
payment nor a debt, and moving a site is an addition. And an entry's **owner
slice may move earlier but never later**: deferring a debt towards the cutover is
not shrinking the ledger, it is #155 §17's failure with an extra step.

The ledger reaches zero at slice 8, before platform admission. It is a finite
migration plan, not permission for the old architecture to survive.

### Adding entries: the reviewed override

Seeding is a normal part of installing a gate — #203 installs the four
model-naming gates and records what they find in the same pull request. So the
ratchet does not forbid additions; it forbids *unreviewed* ones. Add a
`seeding_authorisations` entry naming the gate, the issue, how many entries it
adds and why:

```yaml
seeding_authorisations:
  - gate: G9
    issue: 203
    entries_added: 3
    reason: >-
      This pull request installs `db_table == canonical(model_name)` and records
      the three tables that violate it today.
```

Three things make this an override rather than a formality. It must be **new in
this change** — an authorisation carried over from the base branch licenses
nothing, so the list is an audit trail rather than standing permission. Its count
must be **exactly** how many entries arrived, because a reviewer approves a
quantity, not an intention. And an authorisation that licenses **nothing** fails
too: an override that overrides nothing is the same shape as a check that cannot
fail.

### Why the exceptions are a separate file

`ConnectOAuthState → ubb_connect_oauth_state` is a deliberate exception with a
stated reason: OAuth is a single acronym token, and mechanical snake-casing
yields the worse `ubb_connect_o_auth_state`. Nobody is going to rename it, in
slice 8 or ever.

That is **not a debt anybody owes**, and mixing it into the ledger would make
"the ledger is at zero" unachievable by construction — while G22, slice 8's
completion gate before platform admission, depends on zero being reachable.

The separation is structural rather than a convention: an exception carries no
`owner_slice` and no `expected`, because no rename is coming, and the schema
refuses one that claims either.

## Both files are empty today, and that is the truth

Rule 2 is why. Four gates are installed as this lands — G1 and G5 (the registry's
validity and its generated artifacts) and G15 and G16 (the spec and SDK
ratchets) — and the tree violates none of them. Every gate seeded with today's
violations is still *owed*: G9's three table names and G7's retired words arrive
with #203 and #206, in the same pull requests that install the gates which find
them.

The machinery is complete and proven by negative controls that put synthetic
violations through the real entry point. What it has to say about today is
nothing.

## Beyond what #201 asked for

Four rules here are stricter than the ticket's acceptance criteria. None
contradicts one; each was added because the mechanism is hollow without it. They
are listed so a reviewer sees them rather than discovers them.

1. **An entry may only name an `installed` gate** (and so may an exception).
   #191 §5 rule 2 asks only that an entry name a real gate and a real slice. The
   stricter form is what makes every entry falsifiable — and it is why both lists
   ship empty rather than seeded with hand-typed guesses about gates nothing runs.
2. **An entry's owner slice may move earlier but never later.** Rule 1 as written
   catches additions. Silently editing `owner_slice: slice_2` to `slice_7` adds
   nothing and shrinks nothing, and it is #155 §17's failure with an extra step.
3. **A seeding authorisation's count must match exactly, and one that licenses
   nothing fails.** "An explicit, reviewed override" with no quantity is an
   intention; with no effect it is the inert-suppression defect the spec gate
   already catches in `openapi/`.
4. **The `obligations:` section.** #201 makes `deferred_obligation` one of three
   statuses, and no §8 gate carries it — it would have been dead vocabulary in a
   manifest whose job is that nothing gets lost. O2 and O3 are ADR-0008 §6's two
   admission acts; O1 is the acceptance audit §9 establishes, carried here for
   the same reason ADR-0008 gives for the others: *never silently marked passed.*

## What none of this proves

Every gate in ADR-0008 §8 is a **consistency** check, and this manifest is a
consistency check over those. ADR-0008 §9's sentence applies here without
softening:

> A green CI board proves the declared invariants passed. It does not prove that
> the declarations themselves remain meaningful, complete or commercially
> appropriate.

A row can be perfectly armed, actually running, and assert something not worth
asserting. That question belongs to the one owned acceptance audit — recorded
here as obligation `O1`, precisely so it cannot be mistaken for something a gate
settled.

And one gap specific to these files, flagged rather than buried:

**`landed` is declared, and nothing observes it.** Rule 3 — an entry whose owner
slice has landed fails CI — fires off `slices.yaml`, and no check in a hermetic
suite can see that a GitHub issue closed. If a slice lands and nobody flips its
flag, rule 3 and `LANDED_SLICE_OWNS_GATE` sit inert: exactly the *"everyone
assumed somebody else owned it"* they exist to close, one level up.

The flip is therefore part of the landing slice's own work, alongside its
manifest rows — see *Flipping a row* above. It is not automatable without
putting a network call inside a gate, which would trade a silent gap for a flaky
one. Making the obligation visible is the mitigation, not a fix.
