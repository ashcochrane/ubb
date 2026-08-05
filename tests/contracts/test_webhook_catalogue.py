"""The webhook catalogue is named for the state entered (#205).

G8 in `gates/manifest.yaml`, from ADR-0006 §5. Two properties, settled from one
read of the catalogue against the vocabulary registry:

- **Shape** — every event is `<domain owner>.<state entered>`. The namespace
  belongs to the resource whose lifecycle moved or to the declared control
  family whose own state changed, never to a product and never to the mechanism
  that fired; the transition names a state UBB enters, never the cause, which
  travels as `reason_code` and `trigger_source`.
- **Task** — every `task.*` and `subtask.*` event names a `task_status` value,
  so a terminal Task event maps to a status a Task can actually be in.

**Why this suite and not the platform one.** The gate reads `schemas.py` with
`ast` and never imports it, so it needs no Django, no settings and no database
— and its oracle is `domain-vocabulary/`, which is what this suite is for. It
also means the migration ledger is read directly rather than mirrored: unlike
#203's model-naming gates, which run where PyYAML is not available and therefore
need `test_model_naming_ledger_agreement.py` to hold two encodings together,
there is exactly one copy of the excused list here.

**This gate installs over a catalogue that violates it twenty times**, and #205
renames none of them. That ordering is the point rather than an embarrassment: a
gate installed before the code complies is what makes the vocabulary impossible
to regress (#155 §3.1). Every one of the twenty is an individually identified
ledger entry naming the slice that removes it, and section 1 proves each is
still a real violation — so an entry cannot outlive the debt it records.

**Why no mock.** Every control below builds a real repository on disk and runs
the real entry point over it. A control that patched the reader would reproduce
the reader's mistakes, which is exactly how three SDK methods calling routes
that existed nowhere stayed green for months.
"""

import pytest
import yaml

from _helpers import REPO_ROOT
from _webhook_helpers import (
    CATALOGUE_PATH, DECLARED_EVENTS, catalogue_module, excusing,
    write_repository,
)
from tools.webhook_catalogue import GATE, LEDGER_PATH, assess
from tools.webhook_catalogue import errors as codes
from tools.webhook_catalogue.shape import NON_TERMINAL_TASK_STATUS

#: The faults that mean a name is the wrong shape. Named as a set so the first
#: test asserts on that property rather than on "no errors at all", which would
#: also go red for an unreadable ledger and say the wrong thing about why.
SHAPE_FAULTS = frozenset({
    codes.NAME_MALFORMED, codes.OWNER_NOT_A_DOMAIN_OWNER,
    codes.TRANSITION_NOT_A_DECLARED_STATE,
})

#: How many events #205 found in violation. A CEILING only: the ledger only
#: shrinks, so the day slice 6 renames `billing.balance_low` and deletes its
#: entry this must fall to 19 without anything going red for complying.
#:
#: The floor comes from `test_the_ledger_records_exactly_what_the_gate_excuses`
#: instead, and self-updates: it compares the gate's excuses against the ledger's
#: own entries, so a gate that silently stopped finding violations reports an
#: empty set against a non-empty file. A count pinned here would have had to be
#: edited by every slice that pays one.
SEEDED = 20


@pytest.fixture(scope="module")
def shipped():
    """The gate's verdict on the tree as committed."""
    return assess(REPO_ROOT)


def codes_in(errors, wanted):
    return [error for error in errors if error.code in wanted]


def rejection(tmp_path, **kwargs):
    """Build a synthetic repository and return the errors it must produce.

    Through `assess`, the entry point CI calls, so a failing control fails for
    the reason a failing build would. Fails the test if the tree is clean.
    """
    write_repository(tmp_path, **kwargs)
    _, errors = assess(tmp_path)
    assert errors, "this repository was supposed to be refused, and was not"
    return errors


def accepted(tmp_path, **kwargs):
    """The same, for a repository that must be judged clean."""
    write_repository(tmp_path, **kwargs)
    catalogue, errors = assess(tmp_path)
    assert not errors, "\n" + "\n".join(str(error) for error in errors)
    return catalogue


# ---------------------------------------------------------------------------
# 1. The shipped tree
# ---------------------------------------------------------------------------

def test_every_event_is_named_for_the_state_entered(shipped):
    """G8's shape half. One domain owner, one state — or the ledger owes it."""
    catalogue, errors = shipped
    wrong = codes_in(errors, SHAPE_FAULTS)
    assert not wrong, (
        "\n" + "\n".join(str(error) for error in wrong)
        + f"\n\nAn event name that is not `<owner>.<state entered>` is either "
          f"wrong or must be recorded in {LEDGER_PATH} against {GATE}, owned by "
          f"the slice that renames it.")


def test_every_task_event_maps_to_a_status_value(shipped):
    """G8's Task half. A `task.*` event announces a state a Task can be in."""
    _, errors = shipped
    wrong = codes_in(errors, {codes.TASK_EVENT_WITHOUT_A_STATUS})
    assert not wrong, (
        "\n" + "\n".join(str(error) for error in wrong)
        + "\n\nADR-0006 §5 names the event for the state entered, so a Task "
          "event whose transition is not a `task_status` value describes "
          "something the Task never became.")


def test_the_declared_end_state_obeys_the_rules_it_supplies(shipped):
    """The registry is held to its own shape, not merely consulted about it.

    Two of the three conjuncts are satisfied by construction here — the legal
    owners and transitions are derived FROM these values — but the Task one is
    not. So a future `task.limit_reached` is refused at the moment somebody
    declares it, rather than at the moment something publishes it.
    """
    catalogue, errors = shipped
    declared = catalogue.vocabulary.declared_events
    wrong = [error for error in errors if "domain-vocabulary" in error.location]
    assert not wrong, "\n" + "\n".join(str(error) for error in wrong)
    assert len(declared) > 30, (
        f"the registry declares {len(declared)} events, and #202 landed the "
        f"complete end-state catalogue — this rule is checking almost nothing")


def test_every_seeded_entry_is_still_a_real_violation(shipped):
    """A seeded debt cannot outlive the violation it records.

    `assess` reports an excuse nothing matches, so paying a debt and deleting
    its entry are one act. Without this, the ledger would go on suppressing an
    event that had already been renamed — a suppression the ratchet cannot see,
    because removing an entry is always allowed and adding one back is not.
    """
    _, errors = shipped
    stale = codes_in(errors, {codes.EXCUSE_NOT_A_VIOLATION})
    assert not stale, "\n" + "\n".join(str(error) for error in stale)


def test_the_ledger_records_exactly_what_the_gate_excuses(shipped):
    """The ledger's G8 entries and the gate's excuses are the same list.

    Both directions. An entry the gate never used is caught above; this catches
    the reverse — an event the gate excused that the ledger does not carry,
    which could only happen if the reader silently widened.
    """
    catalogue, _ = shipped
    document = yaml.safe_load(
        (REPO_ROOT / LEDGER_PATH).read_text(encoding="utf-8"))
    recorded = {(entry["site"], entry["found"])
                for entry in document["entries"] if entry["gate"] == GATE}
    assert catalogue.excused == recorded
    assert len(recorded) <= SEEDED, (
        f"{len(recorded)} {GATE} debts, and #205 seeded {SEEDED}. The ledger "
        f"only shrinks; adding one is refused by the ratchet without a seeding "
        f"authorisation, and this catches the case where one was written "
        f"anyway.")


def test_every_expected_name_is_one_the_registry_declares(shipped):
    """A debt is paid by taking an end-state name, so it has to name one."""
    _, errors = shipped
    wrong = codes_in(errors, {codes.EXCUSE_EXPECTED_NOT_DECLARED})
    assert not wrong, "\n" + "\n".join(str(error) for error in wrong)


def test_the_reader_visited_the_whole_catalogue(shipped):
    """Vacuity guard: a gate that reads nothing passes everything.

    Names a floor and two events, because the failure modes differ. A file that
    stopped resolving reports zero; a reader that stopped recognising the
    attribute reports a subset, and the named events are ones no slice deletes.

    The floor on EVENTS is what belongs here. The floor on violations does not:
    it falls every time a slice pays a debt, and it is already enforced against
    the ledger — see `test_the_ledger_records_exactly_what_the_gate_excuses`.
    """
    catalogue, _ = shipped
    assert catalogue is not None, "the catalogue could not be assessed at all"
    assert catalogue.path == CATALOGUE_PATH
    assert len(catalogue.events) >= 35, (
        f"read only {len(catalogue.events)} events, and the catalogue has 35")
    published = {event.name for event in catalogue.events}
    for expected in ("usage.recorded", "customer.deleted"):
        assert expected in published, f"the reader did not see {expected}"
    assert len(catalogue.violations) <= SEEDED, (
        f"{len(catalogue.violations)} violations, and #205 recorded {SEEDED}. "
        f"This only ever falls — a rise means an event was renamed INTO a shape "
        f"ADR-0006 §5 refuses.")


# ---------------------------------------------------------------------------
# 2. Negative controls for the shape rules
# ---------------------------------------------------------------------------

def test_negative_control_a_product_may_not_own_a_namespace(tmp_path):
    """The catalogue's commonest defect: `billing` owning the wallet's levels."""
    errors = rejection(tmp_path, events=("billing.balance_low",))
    assert [error.code for error in errors] == [codes.OWNER_NOT_A_DOMAIN_OWNER]
    # `billing` is a declared product, so the message says so rather than
    # falling back on the generic refusal — the diagnosis is registry data.
    assert "PRODUCTS" in errors[0].message
    # And it has to name the owners that ARE legal, or a reader cannot act.
    assert "`wallet`" in errors[0].message


def test_negative_control_an_unknown_namespace_gets_the_general_refusal(tmp_path):
    """Not every wrong owner is a product or a mechanism, and the generic
    message is the one that carries ADR-0006 §5's actual rule."""
    errors = rejection(tmp_path, events=("margin.credited",))
    assert [error.code for error in errors] == [codes.OWNER_NOT_A_DOMAIN_OWNER]
    assert "is not a domain owner" in errors[0].message


def test_negative_control_a_mechanism_may_not_own_a_namespace(tmp_path):
    """A retired control-family spelling gets the sharper of the two messages.

    `budget` named all four spend controls at once and left the vocabulary; an
    event under it says which mechanism fired, which ADR-0006 §5 puts in the
    `control_family` payload field precisely so the name does not.
    """
    errors = rejection(tmp_path, events=("budget.soft_floor_crossed",))
    assert [error.code for error in errors] == [codes.OWNER_NOT_A_DOMAIN_OWNER]
    assert "retired spend-control spelling" in errors[0].message
    assert "control_family" in errors[0].message


def test_negative_control_the_cause_may_not_be_in_the_name(tmp_path):
    """One overloaded event with the reason in its name is the shape §5 refuses."""
    errors = rejection(tmp_path, events=("wallet.credited_after_refund",))
    assert [error.code for error in errors] == [
        codes.TRANSITION_NOT_A_DECLARED_STATE]
    assert "reason_code" in errors[0].message
    assert "trigger_source" in errors[0].message


def test_negative_control_a_task_event_must_name_a_status(tmp_path):
    """The live catalogue's `task.limit_exceeded`, in one line.

    Two faults, not one, and both are reported: `limit_exceeded` is neither a
    state this catalogue enters nor a state a Task can be in. A reader fixing
    one at a time would otherwise need two runs to learn that.
    """
    errors = rejection(tmp_path, events=("task.limit_exceeded",))
    assert sorted(error.code for error in errors) == sorted([
        codes.TRANSITION_NOT_A_DECLARED_STATE,
        codes.TASK_EVENT_WITHOUT_A_STATUS])
    task = codes_in(errors, {codes.TASK_EVENT_WITHOUT_A_STATUS})[0]
    assert "`killed`" in task.message and "`expired`" in task.message
    assert f"`{NON_TERMINAL_TASK_STATUS}`" not in task.message, (
        "the message lists the TERMINAL statuses, and `active` is not one")


def test_negative_control_a_subtask_event_is_held_to_the_same_rule(tmp_path):
    """One model, one status set, one rule — a Subtask is a Task with a parent."""
    errors = rejection(tmp_path, events=("subtask.limit_exceeded",))
    assert codes_in(errors, {codes.TASK_EVENT_WITHOUT_A_STATUS})


def test_negative_control_a_malformed_name_is_refused_once(tmp_path):
    """Not `<owner>.<transition>` at all — and reported as one fault, not four.

    An unsplittable name has no owner and no transition to judge, so running the
    remaining rules over the pieces would produce three more messages about
    something that was never a webhook name.
    """
    for name in ("usage", "a.b.c", "Usage.Recorded", "usage."):
        errors = rejection(tmp_path, events=(("Synthetic", repr(name)),))
        assert [error.code for error in errors] == [codes.NAME_MALFORMED], name


# ---------------------------------------------------------------------------
# 3. Negative controls for the read itself — the vacuity failure modes, proved
#    rather than asserted. Each is a way the gate could pass while checking
#    nothing, which is the shape this repository has already shipped three times.
# ---------------------------------------------------------------------------

def test_negative_control_an_empty_catalogue_is_a_failure_not_a_pass(tmp_path):
    errors = rejection(tmp_path, events='"""No events here."""\n')
    assert [error.code for error in errors] == [codes.CATALOGUE_EMPTY]


def test_negative_control_a_missing_catalogue_is_a_broken_oracle(tmp_path):
    """A deleted catalogue fails as a REGISTRY fault, and that is the design.

    The registry refuses a declared consumer whose path is not in the
    repository, so the rule "the catalogue file exists" is already enforced,
    once, where consumer paths are declared. A second copy of it in this gate
    would be a branch nothing could reach — the same shape as a check that
    cannot fail. What matters is that the deletion is refused and the message
    names the file, and both are asserted here.
    """
    write_repository(tmp_path)
    (tmp_path / CATALOGUE_PATH).unlink()
    catalogue, errors = assess(tmp_path)
    assert catalogue is None
    assert [error.code for error in errors] == [codes.REGISTRY_UNREADABLE]
    assert CATALOGUE_PATH in errors[0].message


def test_negative_control_a_catalogue_that_does_not_parse_is_reported(tmp_path):
    errors = rejection(tmp_path, events="class Broken:\n    EVENT_TYPE = \n")
    assert [error.code for error in errors] == [codes.CATALOGUE_UNREADABLE]


def test_a_failed_read_does_not_report_every_debt_as_paid(tmp_path):
    """One cause, one error — not one cause buried under twenty consequences.

    A catalogue that will not parse holds no events, so every seeded debt looks
    discharged. On the shipped ledger that is twenty "this debt is no longer
    owed" messages, all false, above the single line saying why.
    """
    errors = rejection(
        tmp_path, events="class Broken:\n    EVENT_TYPE = \n",
        ledger=excusing(("BillingBalanceLow", "billing.balance_low"),
                        ("BillingCredited", "billing.credited")))
    assert [error.code for error in errors] == [codes.CATALOGUE_UNREADABLE]


def test_negative_control_a_computed_event_type_is_reported(tmp_path):
    """A name this gate cannot read is never a name it silently skips."""
    errors = rejection(tmp_path, events=(
        ("Computed", 'PREFIX + ".recorded"'),
        "wallet.credited",
    ))
    assert [error.code for error in errors] == [codes.EVENT_TYPE_NOT_LITERAL]


def test_negative_control_two_classes_claiming_one_name_is_reported(tmp_path):
    errors = rejection(tmp_path, events=(
        ("First", '"wallet.credited"'),
        ("Second", '"wallet.credited"'),
    ))
    assert [error.code for error in errors] == [codes.DUPLICATE_EVENT_TYPE]


def test_negative_control_a_missing_concept_stops_the_assessment(tmp_path):
    """The oracle cannot be half there.

    A registry without `task_status` cannot answer the Task question, and a gate
    that carried on would report the shape half as green while silently dropping
    the other — the failure this manifest exists to refuse, inside one gate.
    """
    write_repository(tmp_path, omit=("task_status",))
    catalogue, errors = assess(tmp_path)
    assert catalogue is None
    assert [error.code for error in errors] == [codes.CONCEPT_MISSING]
    assert "task_status" in errors[0].message


def test_negative_control_an_unusable_registry_is_reported_as_the_oracle(tmp_path):
    """An invalid registry is a broken oracle, not a clean catalogue."""
    write_repository(tmp_path)
    (tmp_path / "domain-vocabulary" / "concepts" / "synthetic.yaml").write_text(
        "webhook_event_type:\n  kind: nonsense\n", encoding="utf-8")
    catalogue, errors = assess(tmp_path)
    assert catalogue is None
    assert [error.code for error in errors] == [codes.REGISTRY_UNREADABLE]


# ---------------------------------------------------------------------------
# 4. Negative controls for the ledger, which is what lets this gate ship green
# ---------------------------------------------------------------------------

def test_a_recorded_violation_is_excused(tmp_path):
    """The mechanism the whole seeding rests on, proved in both directions."""
    catalogue = accepted(
        tmp_path, events=("billing.balance_low",),
        ledger=excusing(("BillingBalanceLow", "billing.balance_low")))
    assert catalogue.excused == {
        (f"{CATALOGUE_PATH}::BillingBalanceLow", "billing.balance_low")}
    assert len(catalogue.violations) == 1


def test_negative_control_an_excuse_for_a_paid_debt_is_reported(tmp_path):
    """The event was renamed and the entry stayed. That is a live suppression."""
    errors = rejection(
        tmp_path, events=("wallet.balance_low",),
        ledger=excusing(("WalletBalanceLow", "billing.balance_low")))
    assert [error.code for error in errors] == [codes.EXCUSE_NOT_A_VIOLATION]


def test_negative_control_an_excuse_keyed_on_the_class_alone_does_not_widen(
        tmp_path):
    """Identity is the site AND the name, so a second wrong name is not covered.

    Without this, a class carrying an excused debt could change which wrong name
    it published and stay green — a suppression the ratchet cannot see, because
    removing an entry is always allowed.
    """
    errors = rejection(
        tmp_path, events=(("BillingBalanceLow", '"billing.credited"'),),
        ledger=excusing(("BillingBalanceLow", "billing.balance_low")))
    assert sorted({error.code for error in errors}) == sorted({
        codes.OWNER_NOT_A_DOMAIN_OWNER, codes.EXCUSE_NOT_A_VIOLATION})


def test_negative_control_an_expected_name_must_be_an_end_state_one(tmp_path):
    """`expected` points at where the debt is paid, so it names a real target."""
    errors = rejection(
        tmp_path, events=("billing.balance_low",),
        ledger=excusing(("BillingBalanceLow", "billing.balance_low"),
                        expected="wallet.balance_lowish"))
    assert [error.code for error in errors] == [
        codes.EXCUSE_EXPECTED_NOT_DECLARED]


def test_an_expected_name_may_be_a_split_into_two_events(tmp_path):
    """#140 §4.3's split: one overloaded event is replaced by two states.

    The ledger has to be able to say that, or the two Task debts would have to
    point at half their own payment.
    """
    accepted(tmp_path, events=("task.limit_exceeded",),
             ledger=excusing(("TaskLimitExceeded", "task.limit_exceeded"),
                             expected="task.killed and task.expired"))


def test_negative_control_an_unreadable_ledger_is_reported(tmp_path):
    errors = rejection(tmp_path, events=("billing.balance_low",),
                       ledger="entries: [ unclosed\n")
    assert codes_in(errors, {codes.EXCUSE_UNREADABLE})


# ---------------------------------------------------------------------------
# 5. Positive controls — what this gate deliberately does NOT refuse
# ---------------------------------------------------------------------------

def test_positive_control_the_declared_catalogue_passes_its_own_rules(tmp_path):
    """The synthetic end state is clean, so every failure above is the mutation."""
    catalogue = accepted(tmp_path, events=DECLARED_EVENTS)
    assert not catalogue.violations


def test_positive_control_an_undeclared_name_of_the_right_shape_passes(tmp_path):
    """The whole reason this is a SHAPE gate and not a membership one.

    `wallet.expired` is in no end-state list. Its owner is a domain owner and
    its transition is a state this catalogue enters, so ADR-0006 §5 has nothing
    to say against it — and whether the exact name belongs in the set is G2's
    question, over every surface, once #207 lands the consumers it compares.
    A gate that refused this here would be G2 arriving early and incomplete.
    """
    catalogue = accepted(tmp_path, events=("wallet.expired",))
    assert not catalogue.violations


def test_positive_control_a_task_event_naming_a_status_passes(tmp_path):
    accepted(tmp_path, events=("task.killed", "task.expired"))


def test_the_name_pattern_comes_from_the_registry_not_from_this_gate(tmp_path):
    """The shape rule is registry data, and a control proves it is read.

    If the pattern were hard-coded in the gate, widening the registry's would
    change nothing here — and the two copies would drift silently, which is the
    defect `token_pattern` was carried onto the compiled concept to prevent.
    """
    catalogue = accepted(tmp_path, events=("wallet.credited",),
                         pattern=r'^[a-z_]+\.[a-z_]+$')
    assert catalogue.vocabulary.name_pattern == r'^[a-z_]+\.[a-z_]+$'
    # And under the widened pattern a name the shipped one refuses now splits,
    # so it is judged on its halves rather than rejected as malformed.
    errors = rejection(tmp_path, events=("billing.balance_low",),
                       pattern=r'^[a-z_]+\.[a-z_]+$')
    assert [error.code for error in errors] == [codes.OWNER_NOT_A_DOMAIN_OWNER]
