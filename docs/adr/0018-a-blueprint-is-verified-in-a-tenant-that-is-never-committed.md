# ADR-0018: A Blueprint is verified in a tenant that is never committed, and its verdict is read off the acknowledgements

**Status:** accepted
**Date:** 2026-10-03
**Decision records:** the consolidated Code Builder specification on #184 (four comments,
2026-09-25) — §13 steps 4 to 6 and the Verify operation (a) to (e), and the Testing Decisions'
Seam A · the owner's ruling on #567 (2026-09-23): the refusal is a Verify-boundary rule against
published configuration only · the owner's rulings of 2026-09-25 (Verify is a synchronous
operation, not a stored run; `event_type_not_available` is the name) · #580
**Companion:** ADR-0015 is the snapshot this runs, and its §7 left retention to this ADR; ADR-001
is the import rule materialisation obeys; ADR-0007 §3 is why every name below is final on the day
it ships

## Context

A generated file is stamped with a `configuration_fingerprint`, the name of the snapshot kept when
its Blueprint was resolved (ADR-0015 §2). Verifying it means running that snapshot — never the
configuration in force now — and showing the developer what each recording was acknowledged with.
The specification fixed the order: load the snapshot, refuse an Event Type it does not publish
before any side effect, materialise it somewhere ephemeral, run the lifecycle, answer, discard.

It left four things to the build, each expensive to change once the console's Verify stage reads
the answer: what "ephemeral" is, what materialising needs that the snapshot does not hold, the
shape of the request and the verdict, and how long a snapshot is kept.

## Decision

### 1. The run happens in a tenant that exists only inside one transaction

The run creates a tenant from the three fields a sandbox copies, builds the snapshot's
configuration in it, runs the lifecycle, and rolls the whole transaction back before it answers —
whatever the run found, and on an unexpected error too. Nothing it wrote is ever committed, so
there is nothing to delete and no moment at which another connection can see it.

Two alternatives were measured and refused:

- **The tenant's sandbox.** There is one per tenant and it holds the developer's own
  configuration; running there mixes the two, and discarding takes theirs.
- **A separate tenant, committed and then removed.** Its rows hold `PROTECT` edges a delete must
  get past — a supplier under an Event Type, a declared quantity under a rule, a rule's book — its
  outbox rows would commit and be delivered, and a process
  that died mid-run would leave it behind. The wipe-config sandbox reset, the obvious discard,
  fails today on the first of those edges (#593).

What the rollback cannot reach is outside the database, and the tenant made for the run keeps the
run away from it: spend enforcement is off and no admission bound is declared on it, so neither the
live counter nor the admission window is touched; every effect that waits for a commit — outbox
delivery, the kill of a unit of work that crossed its ceiling, a Stripe call — is discarded with
the transaction; no API key is minted for it. The answer states this (`environment.discarded`).

### 2. It runs the very start, recording and close a tenant's code reaches

The bodies of `POST /tasks`, `POST /metering/usage`, `POST /tasks/{task_id}/close` and
`PUT /task-types` are plain functions of a tenant and a request, called by their routes and by the
run, so a verification cannot pass where the routes would refuse or answer differently. The rest of
the configuration is written by each record's own writer: the catalogue's models, validated as its
routes validate them and published by `EventType.publish`; the Grouping Field registry's service;
the books' own records and `BookService`'s declare and publish. The composition layer may import
every product (ADR-001), and the boundary test is the judge.

### 3. Nothing is added to the snapshot; three things are supplied and stated

The snapshot was shaped to be hashed, and adding to it would move every fingerprint. So the run
supplies, and `environment` states: a customer to record for (`customer_external_id`), a value for
each Grouping Field the kinds of work require (`grouping_fields`), and the moment every stored rule
takes effect (`rules_effective_at`, the run's start — each rule is in force for the run whatever
window it was declared with). A display name, an analytics heading and an event category are not
held and not needed: none decides a cost or a price.

### 4. Two refusals before anything is written, and the rest is a verdict

- **`422 event_type_not_available`** (#567) for a recording of an Event Type the snapshot does not
  publish: undeclared or still a draft when the Blueprint was resolved, or never selected. It
  reads the snapshot, never the live catalogue, and names each in `event_types`. The ordinary
  recording route is untouched: it has no flag and no switch.
- **`409 conflict`** for a stored Blueprint that is not `complete`. A scaffold or a blocked
  Blueprint generates a file that fails fast rather than records, so there is nothing to verify;
  this is #567's point 4 — the artifact's readiness catches it before execution.

Everything after that is a **200**. A recording's verdict is read off its acknowledgement: a
Measurement the Event Type requires for a complete cost that the recording did not carry
(`missing_required_measurement_keys`), a cost that is `unresolved` (the acknowledgement's own
`unresolved_reason` and `uncosted_measurement_keys` name why), or a replay that named a different
event. The replay's null running totals are not a gap. A call of the run that is refused stops the
run and is answered as `refusal`, with the problem it raised. `verified` is true only with no
refusal and every recording complete.

No new closed value set is published: the verdict is booleans and the acknowledgements' own
concepts, so the registry is unchanged.

### 5. A snapshot is kept for thirty days after it was last resolved

Resolving an identity already kept restarts its period; reading or verifying it does not. A daily
task prunes the rest, for every tenant. Thirty days because the snapshot exists for one job —
proving code the developer has just generated — and a pruned fingerprint is recovered by resolving
again, which stores the same content under the same fingerprint. It is bounded at all because
resolving is a Read-floor act. The period is the owner's to change.

### 6. The outcome the run declares is never the verdict

The server ran the work, so it holds the evidence a declaration needs. A run that reaches its close
declares `delivered` — an uncosted recording is still delivered work. A run stopped by a refusal
declares `cancelled` on the Task it started: the run withdrew the rest. Pass and fail are the
verdict's.

### 7. The floor is Write and the audit ledger is not written

Verifying starts, records and closes, which is the footing those three routes floor at. It is
exempt from the audit ledger on the ingestion routes' ground, and more so: nothing it writes
survives the call to be audited.

### 8. What this ADR does not decide

A draft-preview verification (#567 point 3: possible later, labelled, not now). Ordinary
recording's handling of an undeclared Event Type (#568). The agreed price a fixed-price kind needs
to start for a tenant that bills: until the snapshot carries it, such a run is refused at its start
and says so.

## What proves it

| Rule | Test |
|---|---|
| §1 — nothing is left behind, over every table, and the snapshot stays | `ubb-platform/api/v1/tests/test_verifying_a_blueprint.py` — `TestAMatchingSnapshotIsRun`: `test_nothing_it_did_is_left_behind_and_the_snapshot_stays`, `test_a_tenant_with_its_own_sandbox_verifies_and_its_sandbox_is_untouched` |
| §1 — nothing waits to be delivered, against an ordinary recording that does; no key, no credential | same module — `test_nothing_it_did_waits_to_be_delivered`, `test_an_ordinary_recording_does_wait_to_be_delivered`, `test_it_mints_no_key`, `test_no_response_carries_a_credential` |
| §2 — the real acknowledgement, the unit of work and a Subtask | same module — `test_it_records_and_answers_the_real_acknowledgement`, `test_the_unit_of_work_is_started_with_the_required_values_and_delivered`, `test_a_subtask_is_started_recorded_under_and_closed` |
| §2 — the boundary | `ubb-platform/apps/platform/tests/test_product_boundaries.py` |
| §3 — the snapshot, not live configuration | same module — `TestItRunsTheSnapshotAndNotLiveConfiguration`: `test_configuration_edited_and_republished_after_resolving` |
| §4 — the three unavailable cases, before anything is written, and the draft published since | same module — `TestAnEventTypeTheSnapshotDoesNotPublishIsRefused`: `test_an_undeclared_event_type`, `test_a_draft_only_event_type`, `test_an_event_type_published_live_and_absent_from_the_snapshot`, `test_a_draft_published_after_resolving_is_still_refused` |
| §4 — only a complete Blueprint runs | same module — `test_a_blocked_blueprint_is_refused_and_creates_nothing` |
| §4 — a gap is a 200 that names it; a replay's null totals are not one | same module — `test_a_missing_required_measurement_is_named`, `test_a_missing_cost_rate_is_named`, `test_the_replay_names_the_same_event_and_its_totals_are_null` |
| §4 — ordinary recording has no switch | same module — `TestOrdinaryRecordingHasNoVerificationSwitch`: `test_the_recording_request_publishes_no_new_field`, `test_a_verification_flag_sent_anyway_changes_nothing` |
| §5 — retention, and the prune answered as not-found by both routes | same module — `TestASnapshotIsKeptForThirtyDaysAfterItWasLastResolved`: `test_a_pruned_fingerprint_is_not_found_by_the_read_or_by_verify`, `test_one_inside_the_period_is_kept`, `test_resolving_the_same_selection_again_restarts_the_period` |
| §6 — the outcome on a refusal | same module — `test_a_refused_recording_stops_the_run_and_withdraws_the_work`, `test_a_refused_start_stops_the_run_before_anything_is_recorded` |
| §7 — the floor and the exemption | same module — `test_a_read_key_may_not_verify`; `ubb-platform/api/v1/tests/test_role_floors.py` — `test_every_tenant_route_floor_matches_the_carve`; `ubb-platform/api/v1/tests/test_audit_sweep.py` |

## Consequences

The console's Verify stage (#581) posts `records` and renders the answer as given: an
acknowledgement's null amount is no figure, and every id in it names a record that no longer
exists. A future need to verify against something the snapshot does not hold — an agreed price,
a constant's value — is met by the ticket that adds it to the snapshot's configuration, in a
canonical order, moving every fingerprint once.
