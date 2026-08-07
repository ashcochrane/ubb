"""The registry says what the decision records decided (issue #202).

`test_vocabulary_registry.py` proves the registry is internally *valid*. This
file proves it is *complete against its sources* — which is a different
question, and the one #202 exists to answer. A registry that compiled while
carrying three concepts would pass every check there and none here.

These are not new gates. ADR-0008 §8's inventory is twenty-seven rows and this
adds none: the subject throughout is G1's own — the shipped registry — asserted
at the level of what it says rather than whether it parses. Where an assertion
looks like an owned gate's statement, the difference is the subject, and it is
called out at that assertion. #202's assertions about the gate MANIFEST live in
`test_gate_manifest.py`, beside the rest of the manifest's own checks.

What is deliberately NOT asserted is that the decided vocabulary is *right*.
Consistency with a wrong decision is still consistency (ADR-0008 §9), and every
value here traces to a frozen decision record rather than to a judgement made
in this file.
"""

import re

import pytest

from tools.vocabulary import load_registry

from _helpers import REAL_REGISTRY, REPO_ROOT


@pytest.fixture(scope="module")
def registry():
    return load_registry(REAL_REGISTRY, REPO_ROOT)


# ---------------------------------------------------------------------------
# 1. The domains, and the shape every concept declares
# ---------------------------------------------------------------------------

#: #191 decision 1's file list, plus `governance.yaml` for the audit ledger's
#: own vocabulary — which `apps/platform/audit/actions.py` keeps deliberately
#: apart from the webhook catalogue, since the ledger and the queue are
#: independent contracts. Named here so deleting a domain file is a failure
#: rather than a quietly smaller registry.
DOMAIN_FILES = ("economics.yaml", "governance.yaml", "payment-rails.yaml",
                "retired.yaml", "spend-controls.yaml", "tasks.yaml",
                "webhooks.yaml")


def test_the_registry_is_split_across_the_declared_domains(registry):
    assert sorted(registry.files) == sorted(DOMAIN_FILES)


def test_every_concept_declares_its_kind_summary_and_consumers(registry):
    """#202's concept shape. `consumers` may be empty — the registry is
    normative before the code catches up — but the key is required, and the
    compiler reports the empty ones by name so they are legal *visibly*."""
    for name, concept in sorted(registry.concepts.items()):
        assert concept.kind in registry.schema.kinds, name
        assert concept.summary.strip(), name
        assert isinstance(concept.consumers, tuple), name


def test_every_concept_ubb_words_carries_a_label_key_prefix(registry):
    """ADR-0008 §4: the registry owns identity and generates the stable label
    KEY; the console owns the English attached to it. A UBB-authored value with
    no key has nowhere for that English to hang."""
    for concept in registry.concepts.values():
        if concept.declared_values:
            assert concept.label_key_prefix, concept.name


def test_the_registry_carries_the_decided_end_state_not_todays_code(registry):
    """The design, stated as an assertion: on the day this landed the registry
    disagreed with almost the whole codebase (#191 decision 1). These four are
    the disagreement in miniature — if any of them ever matches what the tree
    carried on the day #202 landed, somebody has quietly reverted the registry
    to describe the code instead of the agreed model."""
    assert "external" in registry.concepts["customer_billing_mode"].values
    assert "fixed_component" in registry.concepts["rate_structure"].values
    assert "task_charge" in registry.concepts["usage_event_kind"].values
    assert "recorded_events" in registry.concepts["analytics_measure"].values


# ---------------------------------------------------------------------------
# 2. The ceiling statuses, and their lower-bound rule as data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ceiling_rule(registry):
    rule = registry.concepts["ceiling_status"].value_semantics
    assert rule is not None, (
        "ceiling_status carries no decision rule — #158 §12.3 makes the "
        "lower-bound rule a spend-control safety invariant that belongs in the "
        "registry beside the values, not in a summary above them"
    )
    return rule


def test_the_lower_bound_rule_is_registry_data(ceiling_rule):
    """AC: the ceiling statuses carry their lower-bound rule as data.

    The rule is *evaluated* here, not pattern-matched against prose. #158 §12.3:
    once the known portion of accumulated COGS has reached the ceiling, costs
    still unresolved cannot reverse the answer — unresolved cost may never
    argue a Task back under a ceiling it has already reached.
    """
    reached = dict(a_ceiling_applies=True, known_cogs_at_or_above_ceiling=True)
    assert ceiling_rule.answer(**reached, unresolved_costs_remain=False) \
        == "ceiling_reached"
    assert ceiling_rule.answer(**reached, unresolved_costs_remain=True) \
        == "ceiling_reached", (
        "an unresolved cost bought the Task its way back under the ceiling"
    )


def test_indeterminate_covers_only_the_case_it_names(ceiling_rule):
    """#158 §12.2: `indeterminate` is the inability to evaluate the ceiling —
    reachable only while the known lower bound is still below it."""
    below = dict(a_ceiling_applies=True, known_cogs_at_or_above_ceiling=False)
    assert ceiling_rule.answer(**below, unresolved_costs_remain=True) \
        == "indeterminate"
    assert ceiling_rule.answer(**below, unresolved_costs_remain=False) \
        == "within_ceiling"


def test_no_ceiling_is_not_indeterminate(ceiling_rule):
    """AC: where no ceiling applies the answer is `not_applicable`.

    #158 §12.4 — `indeterminate` means UBB tried and could not tell, never that
    there was nothing to evaluate. The rule must say so for every combination of
    the other inputs, because "no ceiling" cannot depend on cost at all.
    """
    for at_or_above in (True, False):
        for unresolved in (True, False):
            assert ceiling_rule.answer(
                a_ceiling_applies=False,
                known_cogs_at_or_above_ceiling=at_or_above,
                unresolved_costs_remain=unresolved) == "not_applicable"


def test_the_ceiling_statuses_no_longer_spell_a_retired_word(registry):
    """#158 §12.1's whole reason for settling these before the registry was
    committed: the registry is normative, and ADR-0007 §3 forbids parking a
    public value under a name somebody means to correct later."""
    concept = registry.concepts["ceiling_status"]
    assert set(concept.values) == {"within_ceiling", "ceiling_reached",
                                   "indeterminate", "not_applicable"}
    assert set(concept.retired_aliases) == {"within_limit", "limit_reached"}


# ---------------------------------------------------------------------------
# 3. Retired terms are registry data a sweep can consume
# ---------------------------------------------------------------------------

#: #154 §8's retirement table, as the sweep will meet it: whole snake_case
#: tokens. Every row of that table is here or in SENSE_RETIRED below, and the
#: split between the two lists is the point — see `retired_senses` in
#: `domain-vocabulary/schema.yaml`.
SWEPT = {
    "metric", "metric_name", "dimension", "dimension_def", "tags",
    "card_type", "cost_card", "price_card", "budget", "charging_mode",
    "pre_check", "async_ingest", "fast_lane",
    "work_charge", "revenue_mode", "pricing_provenance", "audit_trail",
    "meter_only", "metering_async", "pricing_model",
}

#: The rows of §8 whose retirement is scoped by SENSE. A text sweep cannot
#: apply the scope, so these are carried apart and stay human-judged
#: (ADR-0008 §1). Putting them in the sweep's input would state something false
#: — #154 §3.4 keeps `limit` in the admission-control rejection, ADR-0007 §4
#: uses "operation" for every published route — and would force exclusions
#: broad enough to disarm the sweep, which #154 §14 warns about by name.
#:
#: THREE OF THESE MOVED HERE IN #206, out of SWEPT above, and they moved on
#: evidence rather than on argument: the sweep this list feeds was built, run,
#: and produced 1,069 hits for `flat`, `hold` and `estimate` between them
#: without one of them being the retired sense.
#:
#:   * `flat` is Django's `values_list(..., flat=True)`, about a hundred times.
#:   * `hold` was `LiveCounter.hold`, the atomic accept-time reservation in the
#:     estimate-hold-settle sequence.
#:   * `estimate` was `PricingService.estimate`, the call that precedes it.
#:
#: #239 DELETED BOTH OF THOSE MECHANISMS and re-took the count against the tree
#: it produced. The two words stay here: they survive as the ordinary English
#: verb and noun on every surface they appear, and still name no
#: `pricing_status` value anywhere. The re-taken numbers, the method, and the
#: reading of every residual occurrence are in the registry beside the words —
#: `domain-vocabulary/concepts/economics.yaml`, `pricing_status.retired_senses`.
#:
#: All three were retired as values of `rate_structure` and `pricing_status`,
#: and `pricing_status` is a new concept whose values have never shipped — so
#: there is not one occurrence of either word as a status value anywhere in the
#: tree. Nothing is lost by the move: the value `flat` only ever appears beside
#: the field `pricing_model`, which IS swept, and G2 refuses a consumer that
#: declares a value the registry does not own.
SENSE_RETIRED = {"limit", "operation", "job", "step", "ingest",
                 "flat", "hold", "estimate"}


def test_retired_terms_are_registry_data(registry):
    """AC: the forbidden-term sweep gets a declared input rather than a list
    somebody maintains by memory. `retired_terms` maps a term to the concept
    that replaced it, so "what do I write instead?" is answered by the data."""
    retired = registry.retired_terms
    assert SWEPT <= set(retired), sorted(SWEPT - set(retired))
    for term in sorted(SWEPT):
        assert retired[term] in registry.concepts


def test_every_sense_scoped_retirement_names_the_sense_that_survives(registry):
    """The other half of #154 §8, and why it is a separate list.

    An entry with no surviving sense is a retired alias somebody left out of the
    sweep's input; an entry in the sweep's input that survives elsewhere is a
    false statement in a normative file. Both are refused, so this asserts the
    five that genuinely are scoped carry their account of the survival.
    """
    senses = registry.retired_senses
    assert set(senses) == SENSE_RETIRED
    for term, (concept_name, sense) in sorted(senses.items()):
        assert concept_name in registry.concepts, term
        assert sense.retired_as.strip() and sense.survives_as.strip(), term
    assert not SENSE_RETIRED & set(registry.retired_terms), (
        "a sense-scoped word reached the sweep's input"
    )


def test_the_audit_action_rename_is_carried_as_retired_data(registry):
    """#154 §4.4's ledger rename, which is the one place ADR-004 §2's
    additive-only rule is deliberately spent — a one-time, scoped,
    pre-production exception. The old registrations must be sweep input, or the
    live codebase keeps a second vocabulary purely to read pre-launch history.
    """
    actions = registry.concepts["audit_action"]
    retired = set(actions.retired_aliases)

    assert actions.kind == "closed"
    assert {"budget.set", "dimension.declared", "rate_card.created",
            "rate.added", "revenue_mode.set"} <= retired
    for renamed in ("customer_spend_pool.set", "grouping_field.declared",
                    "pricing_book.created", "cost_rate.added",
                    "pricing_rule.added", "tenant_supplied_revenue.recorded"):
        assert renamed in actions.values, renamed
    # The entry that opens the production ledger. It is registered like any
    # other action because the ledger refuses a name it does not know.
    assert "system.preproduction_model_cutover" in actions.values
    # Deleted outright rather than renamed: the configured input the first pair
    # recorded is now a field of a pricing rule, and the setting the third
    # recorded is gone because posture derives.
    assert {"markup.set", "markup.deleted", "revenue_mode.set"} <= retired
    assert not {value for value in actions.values
                if value.startswith(("markup.", "rate_card.", "budget."))}


def test_the_audit_actions_stay_apart_from_the_webhook_catalogue(registry):
    """`apps/platform/audit/actions.py` states the rule: the ledger and the
    queue are independent contracts, so `api_key.created` the action and
    `tenant.api_key_created` the event are independent names. Two concepts, not
    one — merging them is the thing that rule refuses."""
    actions = set(registry.concepts["audit_action"].values)
    events = set(registry.concepts["webhook_event_type"].values)

    assert "api_key.created" in actions and "api_key.created" not in events
    assert "tenant.api_key_created" in events
    assert "tenant.api_key_created" not in actions


def test_the_webhook_catalogue_rename_is_carried_as_retired_data(registry):
    """#154 §5.4's rename is twenty event names, and every one of them is on a
    living surface today. The sweep is what finds them; this is the input."""
    retired = registry.concepts["webhook_event_type"].retired_aliases
    for term in ("task.limit_exceeded", "budget.threshold_reached",
                 "stop.fired", "soft_floor.crossed", "billing.balance_low",
                 "margin.provider_cost_spike", "auto_topup.requires_action"):
        assert term in retired, term
    assert len(retired) == 20, f"§5.4 renames twenty events, not {len(retired)}"


# ---------------------------------------------------------------------------
# 4. The registry never enumerates what the tenant owns
# ---------------------------------------------------------------------------

#: ADR-0008 §2's list, verbatim in concept form: tenant-created Event Types,
#: Task and Subtask kinds, Grouping Field values.
TENANT_OWNED = ("event_type_key", "task_type_key", "grouping_field_value",
                "measurement_key", "metadata_key")


def test_the_tenant_defined_concepts_carry_no_value_list(registry):
    """AC: a test proves the tenant-defined concepts carry no value list.

    Map #137 constraint 5 as an assertion over the shipped registry, not only
    as a schema rule — the schema forbids the fields, and this proves the
    concepts the constraint actually names are declared that way rather than
    quietly promoted to closed sets somewhere.
    """
    for name in TENANT_OWNED:
        concept = registry.concepts[name]
        assert concept.kind == "tenant_defined", (
            f"{name} is {concept.kind}: UBB has started owning a set the "
            f"tenant defines"
        )
        assert concept.declared_values == ()
        assert concept.label_key_prefix is None, (
            f"{name} declares a label key — the tenant authored the value, so "
            f"UBB has no wording to supply for it"
        )


def test_free_text_is_recorded_as_not_being_vocabulary(registry):
    """The fourth kind earns its place by answering the question once. Every
    one of these is prose a human typed or an opaque caller token, and each is
    somewhere somebody would otherwise propose an enum."""
    free_text = {concept.name for concept in registry.of_kind("free_text")}
    assert {"plan_name", "external_task_id", "reason_detail"} <= free_text
    for concept in registry.of_kind("free_text"):
        assert concept.declared_values == ()


# ---------------------------------------------------------------------------
# 5. Payment rails: the names land before the machinery
# ---------------------------------------------------------------------------

def test_the_payment_rail_vocabulary_is_declared_closed(registry):
    """AC: payment-rail vocabulary and its environment values are `closed`.

    ADR-0008 §10.4 requires these names to exist before anything is built on
    them, and ADR-0007 §3 forbids parking them under a provisional name — so
    they are declared here and built in slice 8.
    """
    rail = registry.concepts["payment_rail"]
    environment = registry.concepts["payment_rail_environment"]

    assert rail.kind == "closed" and rail.values == ("stripe",)
    assert environment.kind == "closed"
    assert set(environment.values) == {"test", "live"}


def test_the_payment_rail_concepts_are_visibly_unconsumed(registry):
    """The honest state, asserted rather than assumed. Nothing consumes these
    yet; a registry that hid the fact would be claiming coverage it does not
    have, and the compiler reports them by name for the same reason."""
    assert set(registry.concepts_without_consumers) == {"payment_rail",
                                                        "payment_rail_environment"}


# ---------------------------------------------------------------------------
# 6. The catalogue obeys the convention it declares
# ---------------------------------------------------------------------------

EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def test_every_declared_webhook_name_is_owner_dot_past_tense(registry):
    """ADR-0006 §5's shape, over the REGISTRY's catalogue.

    Not G8, which is #205's and whose subject is the shipped catalogue in the
    platform's own module. This is narrower and earlier: the registry is what
    #205 will check that catalogue against, so a mis-shaped name authored here
    would be a broken oracle rather than a finding.
    """
    catalogue = registry.concepts["webhook_event_type"]
    assert catalogue.kind == "closed"
    assert len(catalogue.values) >= 30, "the catalogue lost most of itself"
    for value in catalogue.values:
        assert EVENT_NAME.fullmatch(value), value


def test_every_terminal_task_event_maps_to_a_status_value(registry):
    """ADR-0006 §5's second clause, on the same narrower subject.

    `task.killed` and `task.expired` exist as separate events precisely so a
    subscriber alerting on spend incidents stops being paged when a worker dies
    (#140 §4.3) — which only works if each one names a state the Task can
    actually be in.
    """
    statuses = set(registry.concepts["task_status"].values)
    terminal = [value for value in registry.concepts["webhook_event_type"].values
                if value.split(".")[0] in ("task", "subtask")]
    assert terminal, "no terminal Task events in the catalogue"
    for value in terminal:
        assert value.split(".", 1)[1] in statuses, value
