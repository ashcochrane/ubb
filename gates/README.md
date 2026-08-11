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
| `forbidden-term-sweep.yaml` | G7's declared plan (#206) — where the sweep looks, and the enumerated, counted exclusions where it deliberately does not. |

Everything here except the last is read by `tools/gates` and checked by
`tests/contracts/test_gate_manifest.py` and
`tests/contracts/test_migration_ledger.py`. `forbidden-term-sweep.yaml` is read
by `tools/forbidden_terms` and checked by
`tests/contracts/test_forbidden_terms.py` — it sits here because it is gate
bookkeeping like the other five, and the compiler's "nothing reads this" rule
knows it by name rather than ignoring it.

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

## What the two files hold today

Rule 2 is what decides this. A gate seeded with today's violations records them
in the same pull request that installs it, never before — so the ledger fills up
as slice 0 proceeds rather than arriving pre-written.

| Landed | Gates installed | Ledger | Exceptions |
|---|---|---|---|
| #201 | G1, G5, G15, G16 — and the tree violates none of them | empty | empty |
| #203 | G9, G10, G11, G12 — the model-naming rules | **6** | **1** |
| #204 | G17, G18 — the SDK's two-way operation check | **9** | 1 |
| #205 | G8, G13 — the webhook catalogue's shape, and Celery import discipline | **29** | 1 |
| #222 | — (thirteen webhook renames paid) | **16** | 1 |
| #206 | G7 — the forbidden-term sweep | **175** | 1 |
| #227 | G2, G3 — the consumer census | **229** | 1 |
| #208 | G4 — the contract's known-value metadata | **258** | 1 |
| #210 | G6 — the console's label catalogue, both ways | **302** | **3** |

#203's six are the `Rate`/`RateCard` table inversion and
`ubb_customer_sub_item` (G9), the two `markup_percentage_micros` columns where
`_micros` means millionths of a percent (G11), and `Rate.pricing_model` (G12).
G10 seeds nothing: no writable `tenant_posture` column exists, which is why it
ships with a negative control rather than an entry. The one permanent exception
is `ConnectOAuthState`, and it is an exception to the *mechanism* — mechanical
snake-casing produces a worse name than the one in place — not to the rule.

#204's three are the SDK's dead rate-card calls — a PUT on the flat
`/pricing/rate-cards/{card_id}` path the #86 sweep re-nested, a lineage
`/history` read, and a `/batch` create — all owed by slice 4, whose Pricing Book
replaces the surface they are the ergonomics for. **G18 seeds nothing**, and
that is a ruling rather than an omission: ADR-0007 §4 states the count of
unwrapped operations need not reach zero, so an unwrapped operation is not a
debt anybody owes, and recording 56 of them here would make the ledger
unreachable at zero by construction — the same argument that keeps the permanent
exceptions in their own file. They are signed for in
`ubb-sdk/coverage-authorisations.yaml` instead, which is an audit trail of
reviewed increases and not a third list of debts.

#205's twenty are the largest single seeding, and the number is the absence of a
convention rather than decay: ADR-0006 §5 fixed one on 2026-08-03 and the
catalogue predates it. All twenty, by fault: eight are owned by the product
`billing` rather than by the wallet, the grant or the customer whose state
changed; four are owned by a mechanism (`stop`, `soft_floor`) and one by a
retired spend-control family (`budget`); two are owned by a measure (`margin`)
rather than by the customer and the provider the alerts are about; two put a
bound in the name where a Task status belongs; two file the invoice's own state
under `usage`, the thing that produced it; and one concept is spelled two ways
across this catalogue and the audit registry (`auto_topup` here, `auto_top_up`
there). **#205 renames none of them.** An event
name is a public contract, so the rename belongs to the slice that rebuilds the
event's subject and can carry the spec, the SDK and the console with it in one
vertical. **G13 seeds nothing**: no module in the tree binds the bare word
`tasks`, so it ships with negative controls instead of entries, exactly as G10
does.

**#222 then paid thirteen of the twenty, and G8's ledger stands at seven owed by
slices 5 and 6.** The thirteen were the ones with no subject being rebuilt —
every `billing`, every `margin`, both invoice events and the spelling — so
"belongs to the slice that rebuilds the subject" named no slice for them, and
seven had landed on slice 8 by default against a ticket that says nothing about
renaming public events. Answering that with one act rather than four is
ADR-0006's Consequences applied literally: the v1 contract breaks deliberately
*once*, and map #137 constraint 1 makes a clean break available exactly once.
What remains is not renameable in the same sense — the two Task events SPLIT
into `killed` and `expired` (#140 §4.3) and the five control events are rewritten
under #150's four families, so each needs its slice's work first.

**#206 then installed G7 and seeded 159 entries — the largest seeding by an
order of magnitude, and the whole re-model stated as arithmetic**: 50 of the
registry's 70 retired terms, still present across six areas of the tree. Its
`site` is `<area>::<term>` and its `found` is a file count, which are the two
decisions worth knowing about. Per (area, term) is 159 rows where per file
would be 1,340 and per term alone would be 50 — and the middle one is the only
granularity that both survives eight slices of file movement *and* refuses a
word crossing from the backend to the SDK. A file count rather than a line
count for the same reason: a line count moves whenever anyone edits a line, so
no ratchet could stand on it, while the file count moves exactly when a retired
word reaches somewhere it was not. That is #203's review finding — an excuse
keyed on the site alone stays green when the violation moves — closed here in
the form this gate takes.

The count is checked in **both** directions. Too low and the word has spread;
too high and the entry is an excuse with no upper bound, because the ratchet
compares entry identities rather than their contents and would never see a
`999` typed into one. So paying part of a debt means editing its number — the
change being recorded, not an inconvenience.

Three words moved OUT of the sweep's input in the same change rather than into
the ledger. `flat`, `hold` and `estimate` produced 1,069 hits between them and
not one was the retired sense: `flat` is Django's `values_list(..., flat=True)`,
`hold` was `LiveCounter.hold`, `estimate` was `PricingService.estimate`. They are
now `retired_senses`, which is #202's own stated rule applied — a word retired
in one sense while live in another "would force the sweep into exclusions broad
enough to disarm it". **This is the ticket's largest judgement call and it
weakens what G7 can catch**, so it is recorded here rather than left in a diff.

**#239 deleted both of those mechanisms and re-took the count.** The exclusion
survives it: `hold` and `estimate` are now the ordinary English verb and noun
on every surface they appear, so the classification holds on evidence taken
against the current tree rather than inherited from #206's. The numbers, the
method behind them and the reading of every residual occurrence are recorded
beside the words themselves, in `domain-vocabulary/concepts/economics.yaml`.

It costs exactly one live occurrence, and that is written down too:
`ProductFeeConfig.fee_type == "flat"` is the retired sense, and no gate now sees
it — G7 because the word is not input, G2 because `fee_type` is a bare
`CharField` the registry declares no concept for. **An undeclared public value
set is the finding**, not a sweep gap: #191 story 15 requires a public value to
declare its kind before it ships. **#227 settled it by taking story 15's other
way out** — the field is not public, so no concept is owed and the reason is
under test rather than written down; see the entry for #227 below.

And one entry has **no positive owner**: `meter_only` is owed by slice 8 because
no slice's issue says it rebuilds `customer_billing_mode`, and the mode's
siblings gate on payment-rail activation, which is slice 8's. That is #205's
residue in a new place — an owner nobody chose — and it wants an owner's eye.

**#227 then installed G2 and G3 and seeded fifty-four — the whole re-model
stated from the consumers' side.** `domain-vocabulary/consumers.yaml` had
already promised these entries: a declared consumer is an **end-state**
consumer, and *"every disagreement that survives is a migration-ledger entry
naming the slice that removes it"*. The census asks one question of each — does
this consumer hold the concept's values **by reference** to the generated
artifact? — and the answer today is no, 54 times: 47 `closed` concepts under G2
and 7 `open` ones under G3, over the backend's 29 declared consumers, the
console's 20 and the SDK's 5. Two sites hold anything at all, both from #200,
and both are recorded with what they have already paid.

Its `site` is `<consumer path>::<concept>` and its `found` is `<held> of <total>
values`. Per (file, concept) for the reason #206 chose (area, term): per value
would be 338 rows churning whenever a value moves, and per file would let one
concept's debt hide behind a neighbour's. The count is checked in **both**
directions, exactly as G7's is — the ratchet compares entry identities rather
than their contents, so a `9 of 9 values` typed into one would licence a whole
concept for as long as the entry stood.

**The owner is the slice that rebuilds the concept's SUBJECT, never the slice
that owns the file.** `task_status` is slice 5's whether the consumer restating
it is a Django model, the console or the SDK — #205's rule for event names,
applied to consumers. Two consequences are worth seeing rather than
discovering.

The **console's twenty are not slice 0's**, and #210 is what settles that: *"Slice
0 is complete when the mechanism is active and regressions are impossible — not
when all fifty-two importing files have been rewritten"*, with every remaining
map becoming an individually identified entry carrying an owner and a removal
slice. Seeding them against slice 0 would have been the opposite of what that
ticket asks for.

And **`audit_action` has no positive owner** — the second time this shape has
appeared, after #206's `meter_only`. Its fifty-eight actions name subjects across
every slice, so no one slice rebuilds the catalogue, and it is recorded against
the cutover for want of an owner rather than because anyone chose one. Any slice
may take it earlier; none may take it later.

**What the census cannot see is counted rather than merely admitted.** It walks
the consumers the registry *declares*, so a `choices=` list for a concept
`domain-vocabulary/` says nothing about is invisible to it — and structurally so,
because attributing an enumeration to a concept means comparing its members
against a value set, which is the literal scan #191 decision 3 rules out. So
`tests/contracts/test_undeclared_value_sets.py` pins every `choices=` in living
backend code by file, all 46 across 19 files, and a new one has to come past a
reviewer. That is an **inventory, not a ledger**, and the difference is the same
one that keeps the permanent exceptions in their own file: a ledger entry names
a canonical term and a removal slice, and for most of these neither exists.
Backend only, and stated: `choices=` is Django declaring a closed value set,
while a TypeScript `as const` array is as often a query key as vocabulary — a
pinned count over those would pin noise and get raised until it stopped failing,
which is #154 §14's over-broad exclusion arriving by a different door.

Two things the ticket asked for are recorded in the **manifest** rather than
here, because they are facts about what G2 covers rather than debts anybody
owes. ADR-0005's selector invariant — `Rate.SELECTORS` against the `Posting` —
is **superseded** by G2's registry-backed form, with the existing test left in
place until slice 4 deletes its subject, so that deletion is not later mistaken
for a loss of coverage. And `ProductFeeConfig.fee_type`, #206's one lost
occurrence, **gets no concept**: it is not a public value set, and
`tests/contracts/test_product_fee_type_is_not_public.py` is what makes that
claim falsifiable rather than a note — the day it reaches the spec, the SDK or
the console, #191 story 15 binds and the concept is owed.

**#208 then installed G4 and seeded twenty-nine — a seeding that changes
`openapi/v1.json` by zero bytes, and both halves of that are the point.** The
committed contract begins carrying known-value metadata generated from the
registry according to each concept's kind: an `open` concept's recognised
values as `x-ubb-known-values` beside an untouched `type: string`, a `closed`
one's as a real `enum`, and nothing at all for a concept whose values the
tenant owns. ADR-0003's open-enum stance is not reversed — forcing the spec to
be the vocabulary oracle would turn every new status into a breaking-gate
event, which is the thing that stance exists to prevent.

**The rule that keeps it honest is that the spec advertises a value only where
the backend already SERVES it**, asked through #227's census predicate rather
than a second copy of it. Nothing in the tree serves any concept yet, so the
contract advertises nothing and all twenty-nine concepts the registry says
appear in it are entries here. Emitting the final values on a field that still
returns the retired one would put a falsehood into a *published* document,
which is worse than saying nothing because a consumer can act on it.

Its `site` is `openapi/v1.json::<concept>` and its `found` is the extent the
generated `openapi/known-values.json` records — the same `<held> of <total>
values` shape G2 and G3 use, and **the same owner slice for the same concept**.
That is not a coincidence to be tidied: paying a G4 entry is the second half of
paying that slice's G2 or G3 entry. Convert the consumer, then mark the schema
field — and the spec export *refuses* a marker whose concept the backend does
not serve, so the two halves cannot be done in the wrong order or half done.

**The gate has two halves, and the second is the one worth knowing about.** The
first walks the concept-to-schema mapping the contract itself carries: every
node naming a concept must represent it by its kind. But a *silent* conversion
— somebody typing `Literal[...]` onto a field for an open concept — produces an
`enum` on a node carrying no marker, which that walk would never reach. So
**every `enum` in the committed contract is accounted for by JSON pointer**,
three today, checked in both directions. That is an inventory and not a ledger,
for #206's reason: two of the three enumerate something the registry describes
no concept for, so there is no canonical term to expect and no slice owes a
rename. It is also what makes a new one a reviewer's decision, and the
reviewer's question is the only one that matters here — *is this an open
concept?*

Two entries have **no positive owner**, which is now the third and fourth time
this shape has appeared after #206's `meter_only` and #227's `audit_action`.
`audit_action` arrives again for the same reason, and `customer_billing_mode`
joins it: no slice's issue says it rebuilds the mode, and its siblings gate on
payment-rail activation. Both sit against the cutover for want of an owner
rather than because anyone chose one.

**#210 then installed G6 and seeded forty-two — and the interesting number is
the one it did NOT seed.** The gate has two halves. The coverage half — every
required registry value has wording, in every shipped locale, and every wording
names a live registry value — seeds **nothing**: all 188 keys are authored in
the same change, so that half is at zero on the day it is installed. It is the
first gate here to arrive with its own subject already complete, and the reason
is that wording is cheap to write and impossible to get wrong quietly, which is
not true of a rename.

The forty-two are the other half: what the console still does *instead*. Thirty
hand-written value maps, one hand-written renderer and eleven files importing
the humaniser ADR-0008 §4.3 retires. Its `site` is `<file>::<export>` for a map
and `<file>::humanize` for an importing file — per (file, symbol), one step finer
than #206's (area, term), because unlike a word in prose each of these is a
distinct thing somebody deletes.

**The allowlist and the ledger are one object here, deliberately.** #210's
acceptance criteria ask for two things that read as separate — every remaining
map seeded as an entry with an owner, and the legacy adapter reachable only from
allowlisted sites — and building them as two lists would have produced the exact
shape rule 2 exists to refuse: a suppression list nobody owes, beside a debt list
nothing enforces. One list does both, because the ratchet already refuses an
addition without a reviewed authorisation. One more map is a ledger
addition. That is the whole mechanism.

**Owners are inherited rather than chosen**, which is new here and worth copying.
Nineteen of the forty-two name a concept the registry already declares, and every
one takes the owner slice that concept's own G2/G3 entry already carries — so a
value list and the words for it are owed to one slice rather than two, and no
judgement was exercised. The other twenty-three name `label_key` and sit against
the cutover: the registry declares no concept for a team role or a wallet
transaction type, so naming one in `expected` would be recording a decision
nobody has taken. #210 says outright that the remainder reaches zero at cutover,
and rule 2's "earlier but never later" makes the cutover the only default that
cannot quietly defer a debt. Twenty-seven entries land there in total, which is
the fifth and largest appearance of the no-positive-owner shape — and the first
where the absence is a *registry* gap rather than an unassigned rename.

**One thing here is NOT in the ledger, deliberately.** #210 also asks that new
code may not *reach* the adapter, and fifty-one files imported it then. None is a
separate debt — each imports a map the ledger already owes, and both clear at the
same moment — so seeding them would double the ledger while changing nothing
about when it reaches zero. They are pinned instead as a shrink-only set in
`tests/contracts/test_label_catalogue.py`, which is the same ratchet with no
false debt attached. Worth knowing for the next gate that meets this shape: a
list that only shrinks is the mechanism, and the ledger is one *use* of it.

**And that pin cost two G7 entries, which is the first authorisation here that
licenses growth for a reason other than a gate being installed.** Two of those
files are NAMED after retired concepts, so pinning their paths spells
those words on a surface that did not carry them, and the sweep said so. There
is no version of the list that avoids it — the alternative was pinning a count,
which would let one file be converted while another was added and read as
"nothing happened". So the reach is recorded rather than the sweep weakened, and
both entries are paid by the act that pays their console siblings: rename the
file, and the pinned path follows. Worth noting because the instinct in that
moment is to add a sweep exclusion, and an exclusion would have been invisible.

**Two permanent exceptions, tripling that file.** `subscriptionStatusLabel` and
`planIntervalLabel` word Stripe's vocabulary — Stripe's values, under Stripe's
names, with wording Stripe's own dashboard chose. Map #137 constraint 5 forbids
UBB shipping a vendor catalogue, so the registry must never declare those
concepts, so no label key can ever exist to move them to. A ledger entry for
either would be a debt nobody could pay. They are still *seen*: the gate asserts
each excused site is one the scanner actually reports, so an exception cannot
suppress something that is not there.

**A gate installed in the platform or SDK suite keeps its allowlist there**, in
the language that suite is written in, and a contract test holds the two to each
other. #203's is `test_model_naming_ledger_agreement.py`: the platform suite has
no PyYAML and this one has no Django, both deliberately, so the seeded sites
exist twice and the agreement is checked in both directions including the entry
ids. A site excused in a gate but absent from the ledger would be a suppression
the ratchet cannot see — the failure this whole mechanism exists to refuse.

**A gate installed in the contract suite needs none of that.** G17 and G8 read
this ledger directly, because they are already in a suite with PyYAML, so there
is one encoding and no agreement test to write. Worth noting for whoever installs
the next gate: the mirroring is the cost of a gate living where it cannot read
YAML, not a house style. Its consequence is that each mirroring test covers *its
own* gates — #203's was written to compare every gate with a ledger entry, which
made #204's SDK debts fail inside a Django model walker, and is now scoped to the
four gates that module installs.

G8 is the case that makes the argument concrete: it seeds twenty entries, and
mirroring twenty sites into a Django suite would have been twenty chances for the
two copies to disagree. **And a gate that seeds nothing needs no mirroring
wherever it lives** — G13 runs in the platform suite beside the boundary walker,
which is where its subject is, and has no allowlist in either encoding to hold
together.

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
