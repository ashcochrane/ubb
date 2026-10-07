# ADR-0015: An Integration Blueprint is resolved above the products, kept as a fixture, and addresses a token by where it sits

**Status:** accepted
**Date:** 2026-10-01
**Decision records:** the consolidated Code Builder specification on #184 (four comments,
2026-09-25) — §2 placement, §3 the contract and its field table, §4 the binding classes, §8
readiness, §11 the read-only boundary, §13 the stored snapshot — and the owner's rulings of the same
day (the names, the watch-point that the fingerprint identifies a snapshot that exists) ·
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156 §1, §6, §9, §10) — three questions,
the ordered classification rule, read-and-generate, the server deciding meaning
**Companion:** ADR-001 is the import rule §1 obeys; ADR-0006 §4 is why §3 restates no registry
fact; ADR-0007 §2 owns the transition class §2 declares into, and §3 is why every name here is
final; ADR-0011 §2 is the gate the two routes carry; ADR-0012 is why a kind of work carries no date
in §4

## Context

The Code Builder turns what a tenant has declared into integration code. #184 split it in three:
the server decides what the code must *mean*, a renderer decides how it is *expressed*, and a page
shows both. This ADR records the first of those as built (#576) — the **Integration Blueprint** —
and the four things about it that are expensive to change once a renderer and a console read it.

Two of them were ruled before the build and are recorded here because the code is where they
became facts: where resolution lives, and that resolving stores. Two were left to the build by a
field table that names `arguments[].name` and `configuration_fingerprint` without saying how a
token inside an object-valued field is named, or exactly what the fingerprint is the hash of.

## Decision

### 1. Resolution is composition-layer work, and the kernel keeps what it leaves behind

A Blueprint is resolved from kinds of work and Grouping Fields (kernel, through their read
contracts), the Event Type catalogue (kernel), and the rules that cost and price an event
(metering). Reading the kernel and a product together is what the composition layer is for
(ADR-001 rule 4), so the resolver is `api/v1/integration_blueprint.py` and adds **no channel and
no `queries.py`**.

What a resolution leaves behind is a record, and a record needs an app. It is plain data under a
tenant and imports no product, so it lives in the kernel: `apps/platform/code_builder`. That app
holds the snapshot and the withhold list and resolves nothing.

The two routes mount at `/api/v1/code-builder/`, gated on `metering` like every registry they
resolve.

### 2. Resolving is a `POST` at the Read floor, and it writes exactly one thing

`POST /code-builder/blueprints` **stores**: for a resolution from published configuration it keeps
the resolved content as an immutable, content-addressed snapshot, so the fingerprint a generated
file is stamped with names something that exists. It writes nothing else — no configuration, no
audit entry — and no path through it declares, edits or publishes configuration or performs the
request a diagnostic offers, for an admin exactly as for anybody else.

It floors at **Read**, the one non-GET on the tenant surface that does. What it stores is a derived
test fixture: nothing costs, prices or enforces from it, the only things that read it are the route
that returns one and the verification that will run one, and it may be deleted at any time. A **draft preview** is the same route asked a different question and is
**Admin**'s; it stores nothing and carries no fingerprint.

The snapshot's tenant, fingerprint and content are declared `FROZEN` and a trigger holds them.
Deleting one is deliberately not refused: it is prunable, and a sandbox reset takes it — it is not
in the set a reset keeps, because it is not configuration.

### 3. An argument is one token, named for where it sits

The field table gives an argument a `name` and exactly one of a literal, a parameter or an
environment variable. Classification is per token (#156 §6.1), and one wire field routinely holds
two classes, so:

- **`<field>`** — a published field of the call's request is named for itself (`task_type`); the
  credential every call carries is `api_key`. For a field holding an object of declared keys
  (`grouping_fields`, `measurements`) a token named for the field is one **key** of it, carried as
  the literal;
- **`<field>.<key>`** — the **value** under a declared key. So an entry is two tokens, and a known
  key sits beside a runtime value;
- **`<field>.<element>`** and **`<field>.<key>.<element>`** — a **declared fact** about the value it
  is named under, spelled as the declaration's own published field: `task_type.pricing_mode`,
  `event_type.costing_method`, `measurements.<key>.source_path`,
  `provider_cost_micros.amount_representation`. One is UBB's fact and not the tenant's, and is named
  for its registry concept: `event_type.response_shape_representation`.

**A key is one segment whatever it contains.** A declared key is the tenant's own word and may
hold a dot; a dot or a percent sign inside one is percent-encoded in a name (`.` → `%2E`, `%` →
`%25`). So a name always splits on its dots, and a key that ends like an element cannot be read as
one. The key's own token carries it unencoded.

**The encoding has one implementation**, with its inverse beside it:
`apps/platform/code_builder/token_names.py`. Its round trip and the absence of collisions are
pinned for the separator, for the sign, for the two mixed, for keys that already look encoded and
for keys outside ASCII.

**A renderer consumes the name it is given and never re-implements the encoding.** The tokens named
under a key follow that key's own token directly, sharing one `<field>.<segment>` prefix, so a
consumer pairs them by position and reads the prefix off the name.

**The declared facts are in the document because nothing else serves them.** A Blueprint resolves
an Event Type from what it last published, and the catalogue's routes serve the draft once an edit
lands — so the costing method, each quantity's value type, unit and required flag, and the response
shape would otherwise be readable nowhere. Each carries the declaration it came from, which is what
keeps the document a reading of the registries and not a second holder of their facts.

**They are `platform_known` facts, not runtime inputs.** A renderer may respell one or use it to
choose a branch. It never asks the developer for one again.

The table gains no field for any of this, which is what lets the tickets that lift a blocked case
leave it unchanged.

A literal is untyped JSON. Where one carries a closed concept's value — a pricing mode, a costing
method, a quantity's value type, an amount representation, a response shape's representation — the
contract cannot mark it there. Each is a declared value, marked on the route that declares it where
one does.

### 4. The fingerprint is the hash of the resolved contract, and of nothing presentational

`configuration_fingerprint` means **stable resolved-contract identity**. It is not a hash of every
byte that happened to be serialised (owner ruling, 2026-10-02).

A stored snapshot has two halves, and the fingerprint is `sha256:` and the SHA-256 of the canonical
JSON of the first:

- **`identity`**, hashed:
  - the selection;
  - the Blueprint's machine-readable resolution: `schema_version` and `renderer_contract_version`
    (what is needed to read it), the target, every call and token, each readiness verdict, and each
    diagnostic's `severity`, `code`, `object_kind`, `key` and `field`;
  - the configuration it was resolved from, with the publication each Event Type's facts came from.
- **`presentation`**, kept and **not** hashed: the `remediation_request` each diagnostic offers. It
  is built from the API's own routes and request shapes, so it can change with no change to what
  the tenant configured or to what the code must mean. A registry route gaining a field must not
  make every blocked integration look like a different one.

Canonical JSON is sorted keys, no insignificant whitespace, UTF-8. A list is ordered and its order
is hashed, so every list whose order means nothing is put in a canonical order first.

**What moves it, and is meant to:**

- a changed selection or target;
- a changed declaration, of a kind of work, an Event Type, a Grouping Field, a rule or the markup;
- **a republication, even of an unchanged declaration.** The identity says which publication each
  Event Type was resolved from, because a generated file's header states it. Revise → revert →
  publish moves the revision, and a fingerprint that stayed put would name a header that no longer
  says what the catalogue does;
- a rule scheduled to open or close passing its moment. The identity holds the rules in force now;
- a new `schema_version` or `renderer_contract_version`.

**What does not, and must not:**

- wording. There is none: a diagnostic is a code, and the console words it;
- the `remediation_request` a diagnostic offers;
- order that has no meaning: the order a selection names things in, the order a kind lists its
  required Grouping Fields in, the order a tenant's products are stored in, the order rules sit in
  their table;
- the moment of resolution, and any row's `created_at` or `updated_at`;
- any row's id, and the tenant's. Two tenants with the same configuration hold the same
  fingerprint, each under their own row.

The only instants in the identity are configuration: when an Event Type was published, and when a
rule opens and closes. The order of `calls` is the lifecycle's and is meant.

A kind of work has no publish record and carries no date (ADR-0012); the identity holds what it
declares, so a change to one moves the fingerprint.

Storing is **first-wins on presentation**: an identity already kept is found, and the Blueprint
read back by its fingerprint is the one first answered.

### 5. The fifth question is asked by the Blueprint, not answered to it

#156 lists a conditional fifth input: where the declared values come from in the supplier's
response, where no mapping resolves. The request takes no path. A path is part of an Event Type's
published contract, and a builder that accepted one would be a second place to declare it — on a
route that changes no configuration. Where nothing resolves, the Blueprint answers with a blocking
diagnostic carrying the request that declares it at the surface that owns it.

### 6. The diagnostic codes are a versioned closed set

`diagnostic_code` is closed: a consumer may switch over it exhaustively. It is **not** final
forever. A member is added or removed **in the same commit as the capability change** that makes
its condition reportable or unreportable, so the set never names a state nothing produces and never
fails to name one something does. A test reads the set off the committed contract and holds it
equal to what resolutions actually report; that test is the ratchet.

Seventeen members stand at this commit. Two changes are already expected: the ticket that carries a
cost read off a supplier's response removes `reported_cost_provider_response_unsupported`, and the
ticket that makes a fixed-price kind ready or not adds the member for a missing agreed price.

*Since:* #571 swapped `constant_value_not_declared` for `constant_measurement_not_renderable`, and
#570, which carries that cost on a transport of its own (`provider_response_cost_micros`), swapped
`reported_cost_provider_response_unsupported` for `reported_cost_provider_response_not_renderable`:
the mapping is valid configuration that this Code Builder version cannot yet render, and the ticket
that renders the read (#583) removes it. Both carry no remediation request — nothing in a valid
declaration is the thing to change.

### 7. What this ADR does not decide

How long a snapshot is kept: the Verify ticket set it (#580, ADR-0018 §5 — thirty days after it
was last resolved). How a renderer spells anything.
Whether an unpublished request key should be refused: this route drops one, on the posture every
other route here holds.

### 8. The owner's rulings on this record

The owner reviewed these decisions on PR #594 on 2026-10-02 and approved §1 to §3 and §5 as built.
§4 was approved in what moves the fingerprint (a republication, a rule's moment passing) and
tightened in what must not: the hash boundary above was drawn in answer, taking the
`remediation_request` out of the hash and removing three orders that meant nothing. §6 is the
owner's wording for the codes.

## What proves it

| Rule | Test |
|---|---|
| §1 — the resolver crosses no boundary | `ubb-platform/apps/platform/tests/test_product_boundaries.py` |
| §2 — nothing but the snapshot is written, over every table; the same content is one row | `ubb-platform/api/v1/tests/test_the_integration_blueprint.py` — `TestResolvingStoresTheSnapshotAndNothingElse`: `test_no_table_but_the_snapshots_changes`, `test_the_same_content_is_the_same_fingerprint_and_one_row` |
| §2 — no operation that writes configuration, even for an admin (three operations since #580 added verification, ADR-0018) | same module — `TestTheBuilderChangesNoConfiguration`: `test_the_builder_has_three_operations_and_none_is_a_configuration_write`, `test_an_admin_resolving_a_blueprint_full_of_fixes_applies_none_of_them` |
| §2 — the floors, and what a preview leaves behind | same module — `TestADraftPreviewIsForAnAdminAndLeavesNothingBehind`: `test_a_read_key_resolves_and_reads_but_may_not_preview_a_draft`, `test_it_resolves_the_draft_stores_nothing_and_has_no_fingerprint`; `ubb-platform/api/v1/tests/test_role_floors.py` — `test_every_tenant_route_floor_matches_the_carve` |
| §2 — the database refuses a change through every door and admits a delete | `ubb-platform/apps/platform/code_builder/tests/test_snapshots.py` — `ASnapshotNeverChangesTest`: `test_save_is_refused`, `test_a_queryset_update_is_refused`, `test_raw_sql_is_refused`, `test_a_snapshot_may_be_deleted` |
| §2 — a sandbox reset takes it | `ubb-platform/api/v1/tests/test_the_integration_blueprint.py` — `TestASandboxResetWipesTheSnapshots`: `test_a_reset_removes_them_whether_or_not_it_keeps_configuration` |
| §3 — a known key beside a runtime value; a runtime root and a known path; each class fills its own field | same module — `TestEachTokenHasItsOwnClass`: `test_a_known_key_sits_beside_a_runtime_value_on_one_call`, `test_a_quantity_read_from_the_response_is_a_runtime_root_and_a_known_path`, `test_each_class_fills_its_own_field_and_no_other` |
| §3 — a key is one segment whatever it contains | same module — `test_a_key_is_one_segment_of_a_name_whatever_it_contains` |
| §3 — the declared facts travel with the declaration they came from, and are the published ones | same module — `TestTheSelectionIsTheOnlyInput`: `test_a_kind_of_work_says_how_it_is_sold_and_what_it_may_spend`, `test_an_event_type_says_what_it_published_about_itself`, `test_a_revised_event_types_facts_are_the_published_ones`, `test_the_response_shape_and_what_it_is_travel_with_the_paths` |
| §3 — every bare name is a field its operation publishes | same module — `TestEveryCallNamesARealOperation`: `test_every_bare_argument_is_a_field_its_operation_publishes` |
| §3 — one encoding, with its round trip and no collisions | `ubb-platform/apps/platform/code_builder/tests/test_token_names.py` — `test_a_key_comes_back_from_its_segment_exactly`, `test_a_segment_never_contains_the_separator`, `test_no_two_keys_share_a_segment`, `test_a_name_splits_into_the_segments_it_was_built_from` |
| §3 — the tokens under a key follow its own token, so no consumer needs the encoding | `ubb-platform/api/v1/tests/test_the_integration_blueprint.py` — `test_the_tokens_under_a_key_follow_its_own_token_directly` |
| §4 — what moves the fingerprint: a republication, a changed kind | same module — `test_a_republication_is_a_new_fingerprint_though_the_declaration_is_the_same`, `test_a_changed_kind_of_work_is_a_new_fingerprint` |
| §4 — what it is the hash of, and what must not move it | same module — `TestTheFingerprintIsOfTheResolvedContractAndNothingElse`: `test_it_is_the_hash_of_the_identity_half_of_the_stored_row`, `test_the_request_a_diagnostic_offers_is_kept_and_is_not_hashed`, `test_a_request_spelled_another_way_is_the_same_fingerprint`, `test_the_order_a_kind_lists_its_requirements_in_is_not_part_of_it`, `test_the_order_a_tenant_lists_its_products_in_is_not_part_of_it`, `test_the_rules_are_in_the_order_of_what_they_say`, `test_nothing_volatile_is_in_it`, `test_resolving_again_later_is_the_same_fingerprint`; and `test_the_same_selection_in_another_order_is_the_same_blueprint` |
| §4 — the store hashes the identity half and only that; first wins on presentation | `ubb-platform/apps/platform/code_builder/tests/test_snapshots.py` — `test_the_fingerprint_is_of_the_identity_and_not_of_the_presentation`, `test_an_identity_already_kept_keeps_the_presentation_it_came_with`, `test_it_can_be_reproduced_by_anything_that_can_write_json` |
| §6 — the published set is exactly what resolutions report | `ubb-platform/api/v1/tests/test_the_integration_blueprint.py` — `test_every_published_code_is_one_a_resolution_reports` |
| §5 — the request takes no path, and the question is put as a diagnostic | same module — `TestTheSelectionIsTheOnlyInput`: `test_the_request_publishes_the_selection_and_nothing_else`, `test_where_no_mapping_resolves_the_blueprint_asks_and_takes_no_path` |

## Consequences

- **A second non-GET at the Read floor has to come past the same argument.** The carve keeps the
  exception as a set of one.
- **A fingerprint moves more often than a declaration does.** Republishing unchanged content makes
  a held file stale. That is the price of the header and the fingerprint never disagreeing, and it
  costs a regeneration.
- **The token names are public.** A renderer and a console read them; changing the convention is a
  contract change to both, which is why it is recorded here rather than left in a docstring.
- **A Blueprint read back by its fingerprint offers the requests it was first stored with.** If the
  API later spells a fix differently, a new resolution of the same identity answers the new
  spelling and finds the old row. The two differ only in the half that is not the contract.
- **A closed value can cross inside a literal unmarked.** Five kinds do today (§3 names them).
  Typing them would mean a field per declared element, which the field table deliberately does not
  have.
- **A sandbox reset invalidates every fingerprint resolved in that sandbox.** A developer resolves
  again; with the same configuration that is the same fingerprint.
