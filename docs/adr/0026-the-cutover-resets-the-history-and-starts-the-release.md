# ADR-0026: The cutover resets the history and starts the release — a fresh initial set, its carried rules, no opening audit row, a new API baseline, and SDK v4.0.0

**Status:** accepted
**Date:** 2026-10-29
**Decision records:** #190 spec part 3 (W6) and its appendix · the owner and consultant's rulings of
2026-10-29 on slice 8's window W6, §0.3 points 1–21 and §0.4 · the audit-ledger ruling of 2026-10-23
(#190 comment `6354381879`) · R2, the owner and consultant's close-out review of 2026-10-22 (#190 spec
part 3 §9 and part 4)
**Amends:** #154 §4.2 (`docs/plans/2026-08-03-vocabulary-lock-decision.md`) — *"open the production
ledger with one explicit entry"*, `system.preproduction_model_cutover` — and #155 §11.1 item 2
(`docs/plans/2026-08-03-migration-and-cutover-decision.md`) — *"Audit-ledger reset (#154 §4.2) — …
open with `system.preproduction_model_cutover`."* No opening entry is written. The evidence is the
2026-10-23 ruling: `AuditRecord.tenant_id` is required ("every row is tenant-scoped"), no tenant-less
audit mechanism exists, and at migration time no tenant exists, so the ratified entry could not be
written truthfully; nothing was ever deployed and no tenant audit trail is being cut over. The rest of
both sections stands: the actions were renamed and the dead registrations deleted (R10-W4), and the
pre-cutover rows went with the fresh database.
**Departs from:** ADR-0003 §6 — *"v3.x at launch"*, and a major *"only when the SDK's own surface
breaks"*. The SDK's own surface did break after its pre-release number was set (R10-W3 to W5; the
SDK's `MIGRATION.md` §21–§24), so the first release is 4.0.0.
**Companion:** ADR-0007 §1 (renames carry their data from the squash onward) and §5 (the pre-live
lane) · ADR-0008 §6 (admission) · ADR-0020 §3 (the receipt's schema 2) · ADR-0024 §2 (`withheld_values`)

## Context

The re-model was built in eight slices, a Code Builder and five close-out windows (W1–W5), on 287
migrations that described every intermediate model it passed through. Nothing was ever deployed; the
only databases holding that history are developers' own. Slice 8 is the cutover: the point at which
the finished model becomes the starting point. Four records had to restart at the same commit — the
schema's history, the audit trail, the API's compatibility baseline and the SDK's release line — and
five assertions had to prove the old model gone by tests that can fail.

## Decision

### 1. The schema history restarts as a fresh initial set

All 287 historical migrations, and the two helper modules only they used, are deleted. Each app has one
`0001_initial` generated from its final models — Django needed no split for a cross-app or circular
key — and the six apps that own a database rule have a hand-written `0002_the_database_rules`
(`pricing`, `usage`, `work`, `event_types`, `tenants`, `code_builder`).

- **No `replaces` and no bridge.** A development database is dropped and re-created
  (`CLAUDE.md`, "Running the suite"); pre-launch development data is not product history.
- **All 86 historical data steps are dropped.** None was a seed a fresh installation needs: every one
  derived rows from rows (backfills, guards, mixed), and what a fresh install needs is produced at
  runtime.
- **The schema is the same schema.** An old-chain database and a fresh-set database, each migrated from
  empty, differ in 38 column orders, 80 Django-generated names re-derived from the final table and
  column names, and the 13 final names below — and in nothing else: the same 86 tables, columns, types,
  nullability, defaults, constraint and index definitions.
- **Two existing facts are recorded, not changed:** `Rate.rate_structure` is limited by model and
  application validation only, with no database `CHECK`; and a constant measurement's value inside an
  Event Type's kept publication has no database rule of its own (its in-row half is held by three
  `CHECK`s). Each was so before the cutover. Whether either deserves a rule is a product question, not
  cutover work.

### 2. The 21 database rules are carried, exactly

The triggers and their plpgsql functions live outside Django's migration state, so the squash could not
regenerate them. Each is carried in its app's rules migration as the final installed definition the old
chain left: usage/0049's price-door function with usage/0046's trigger statement, the receipt rule's
re-install on its renamed column, work/0029's composed body, the two rate rules on `ubb_rate`, and the
deferred constraint trigger that keeps an Event Type's held names. Every `pg_get_functiondef` and
`pg_get_triggerdef`, compared between an old-chain database and a fresh one, is identical. Each rule is
one `RunSQL([install], [uninstall])`, passed as a list so that `sqlparse` never strips the comments
inside a body.

**A rules migration depends on the schema leaf of every app owning a table its SQL reads**, never on an
assumed `0001`: the usage rules read `ubb_tenant.is_sandbox`, so the usage rules migration names the
tenants schema leaf itself rather than inheriting it through `usage/0001`'s keys. Every table and
column each rule reads is created by an ancestor of its rules migration in the graph, and the mapping is
stated and held to the SQL in both directions.

### 3. G20 holds every migration after the fresh set

ADR-0007 §1's rule binds "from the cutover squash onward", and G20 is its check. The fresh initial set
(26 files) is named in one constant; every later migration is held: a drop and an add on one model, in
the same migration or two adjacent ones of an app, is refused as a disguised rename whatever its types
unless it declares otherwise with a reason; every drop states its reason; every data step names a
reverse or states why it has none. The scope is stated where the gate is: pairs further apart, a field
moved between models or apps, state-only operations and raw-SQL drops are outside it.

### 4. The final free names

The fresh set creates every living identifier under its canonical name, with no rename owed:
`ubb_customer_subscription_item` (the migration ledger's last entry, G9 — the ledger is at zero);
`uq_grouping_field_key`, `uq_grouping_field_slot`, `uq_grouping_field_value`,
`idx_grouping_field_value_tenant_key` and `TaskType.required_grouping_fields` (W4's handed names);
`uq_posting_idempotency` and the five `idx_posting_*` indexes on the posting; and
`uq_top_up_attempt_idempotency`. `idx_grouping_field_value_tenant_key` is 35 characters, past the 30
Django allows a `models.Index` for cross-database (Oracle) reasons; UBB runs on PostgreSQL alone, whose
identifiers hold 63 bytes, so it is declared through `core.models.PostgresNamedIndex`, a plain btree
index with PostgreSQL's limit, rather than abbreviated.

### 5. The Pricing Receipt is read in one shape

Every reader of an older receipt shape (versions 0 and 1) is deleted. A receipt is valid only at
`receipt_schema_version` 2, and every reader and the completion boundary refuse anything else —
**including the empty record**, which is not a receipt, not an older one, and not the public "no
receipt" (that is `null`, on a batch item that never created a record). Both production creators of a
posting pass a built receipt at insert, so the receipt column's `{}` default was needed by nothing; it
is gone, and a creator that omits the receipt fails at its insert.

**The contract loses the older shapes' null with them** (the owner's review of the first pull request,
2026-10-29). `pricing_receipt_subject_type` was nullable on the acknowledgement and the usage detail
only because a receipt written before the subject was typed carried none. The one construction boundary
refuses a version-2 receipt whose subject is not one of the closed set, so every receipt UBB can hold
states what it explains: the field is **required and never null** on both, and on a batch item it is
required and null only beside a rejected item's null receipt. This is the one contract change the
cutover makes, a tightening of three response fields (no breaking edge against `api-v1-launch` or
`main`), made before §7's baseline is cut so that the baseline does not freeze a state nothing can
produce.

### 6. The audit trail opens with no synthetic row (option (i))

No opening entry is written. The registration `system.preproduction_model_cutover`, which no writer
could ever record, is deleted together with the `withheld_values` line that kept it unadvertised
(ADR-0024 §2's mechanism stays, for the values still withheld). `AuditRecord.tenant_id` stays required,
and every row stays tenant-owned. **The durable cutover evidence is** the cutover commit, the new API
baseline tag, the suppression reset and the `slice_8.landed` flip record. This is a narrow exception
inside #190, not a change to the audit model.

### 7. A new API baseline, measured from the finished model

`api-v1-cutover` is an annotated, immutable tag on the cutover's merge commit on `main`; the cumulative
breaking gate moves to it and both suppression files are reset to their header comments. The tag is cut
after the cutover merges, because it must name a commit already on `main`, so the repoint is the
cutover's second pull request, which may not change the contract it baselines. The baseline is the
first pull request's contract, §5's tightening included. `api-v1-launch` is never
moved or deleted. The dated compatibility note stays until platform admission (W7).

### 8. The SDK's first release is 4.0.0: a tag and a reproducible wheel

The release is the annotated tag `sdk-v4.0.0` on the same commit, and a wheel built reproducibly from
it; nothing publishes it. This is R2's rule (#190 spec part 3 §9 and part 4). The recipe,
`ubb-sdk/release/build_wheel.py`, is committed with the code it builds and runs only as the tag's
own copy: it exports the tag cleanly, verifies the export is the tag's tree byte for byte, and builds
twice on Python 3.13 with `SOURCE_DATE_EPOCH` set to the tagged commit's committer time, refusing on any
difference. **The build environment is the tag's lock and nothing else** (the owner's review of the
first pull request, 2026-10-29): `ubb-sdk/release/build-requirements.txt` pins and hashes every package
the build frontend and the setuptools backend import; the virtual environment is created without pip
and the release Python's own pip installs the lock into it from outside, so the environment holds no
installer and the check that it holds exactly the lock exempts nothing; `pyproject.toml`'s
`[build-system] requires` must be exactly a pin in the lock; and no `PYTHON*`, `PIP_*`, `SETUPTOOLS*`,
`DISTUTILS*` or hook-override setting from the builder's shell reaches the install or the build. The
release evidence names the tag and its commit, the Python's major.minor and exact version, the lock's
SHA-256 with every package it installed, the installer that ran outside the environment, the wheel's
filename and its SHA-256. The tree's
earlier number, 3.0.0, was never released. The Integration Blueprint's Python target names SDK major 4,
so every Python Blueprint's fingerprint moved, the renderer catalogue moved to version 10 because one of
its members did, and the renderer contract stayed 3: what generated code does did not change.

## What proves it

| Claim | Pinned by |
|---|---|
| §2 — the 21 rules installed from empty, each body the carried text, dependencies stated and built by ancestors, the reverse exercised | `ubb-platform/apps/platform/tests/test_the_database_rules_are_carried.py` — `TheFreshSetInstallsEveryRuleTest`, `TheRulesDependOnWhatTheyReadTest`, `TheRulesMigrationsReverseTest` |
| §3 — G20, with its planted renames split across files | `tests/contracts/test_migrations_carry_their_data.py` — `test_every_migration_after_the_fresh_set_carries_its_data`, `test_planted_a_drop_then_an_add_in_the_next_migration_is_a_disguised_rename`, `test_the_scope_is_adjacent_migrations_and_says_so` |
| §4 — the posting's final names; the ledger at zero with G9 still biting | `ubb-platform/apps/metering/usage/tests/test_the_usage_record_is_the_posting.py` — `ThePostingTableCarriesItsKeysAndIndexesTest`; `ubb-platform/apps/platform/tests/test_model_naming.py` — `test_table_name_is_the_canonical_snake_cased_model_name`, `test_negative_control_a_mismatched_table_is_flagged`; `tests/contracts/test_model_naming_ledger_agreement.py` — `test_the_gate_module_exists_and_declares_both_allowlists` |
| §5 — one receipt shape, `{}` refused, an omitted receipt refused at its insert | `ubb-platform/api/v1/tests/test_the_cutover_assertions.py` — `NoLegacyPricingProvenanceIsReadTest`, `EveryNewMonetaryRecordUsesTheNewReceiptShapeTest` |
| §5 — every receipt states its subject: required and never null, null only on a rejected batch item | `ubb-platform/api/v1/tests/test_the_pricing_receipt_is_typed.py` — `EveryReceiptStatesWhatItExplainsTest`; `ubb-platform/apps/metering/pricing/tests/test_the_pricing_receipt_explains_an_amount.py` — `TestTheBoundaryRefusesARecordThatExplainsNothing` |
| §6 — no opening entry, and none can be written | `ubb-platform/api/v1/tests/test_the_audit_catalogue_is_the_registrys.py` — `test_no_opening_entry_can_be_written`, `test_the_recordable_set_is_the_registrys` |
| G21 — the five assertions, each with a planted violation | `ubb-platform/api/v1/tests/test_the_cutover_assertions.py` — `NoOldPostingReachesABalanceOrAReportTest`, `NoUndeclaredMeasurementSurvivesTest`, `EveryNewEventValidatesAgainstItsEventTypeTest`; `tests/contracts/test_no_retired_posting_or_receipt_reader_survives.py` — `test_no_production_sql_reads_an_old_posting`, `test_no_production_code_reads_a_legacy_receipt` |
| §8 — v4.0.0, the recipe's refusals (a backend or package outside the lock, an installer in the environment, an outside setting), the evidence, the Blueprint's major | `ubb-sdk/tests/test_release.py` — `test_sdk_is_v4`, `TestTheReleaseRecipe`; `tests/contracts/test_the_blueprint_targets_the_sdk_that_ships.py` — `test_the_python_target_names_the_major_of_the_sdk_in_this_tree` |

## Consequences

- A developer database built before the cutover cannot be migrated forward; it is dropped and
  re-created, and `seed_dev_data` rebuilds a working tenant under the new model.
- Every later schema change is a migration G20 holds, and the first one states the new count in
  `MIGRATIONS_SINCE_THE_CUTOVER`.
- `system.preproduction_model_cutover` names nothing any more; ADR-0006's consequence sentence and #154
  §4.2 keep their historical words, annotated to point here.
- After platform admission (W7) the dated note in `docs/api-compatibility.md` is deleted and ADR-0003
  §4 governs every break, measured from `api-v1-cutover`.
