"""The vocabulary registry's validity gate (issue #198, ADR-0008 §2).

`domain-vocabulary/` is the checked-in statement of the agreed model. This file
is what makes it normative rather than decorative, in three parts:

1. **The shipped registry is valid**, and the checks that prove it are proven to
   have actually read it (the vacuity guard) — a gate that silently walks
   nothing is worse than no gate, because the board stays green.
2. **Negative controls**: one deliberately broken registry per named reason the
   compiler can reject, each built on disk and loaded through the real entry
   point. A gate with no negative control is a vacuous assertion.
3. **Positive controls**: the legal constructions that must keep passing, so a
   tightened rule cannot quietly outlaw something the model relies on — a
   concept nobody consumes yet, and a kind that declares no values at all.

What is deliberately NOT tested here is whether the registry's declarations are
*correct*. Consistency with a wrong declaration is still consistency; that
question is the one owned acceptance audit's (ADR-0008 §1).
"""

import pytest
import yaml

from tools.vocabulary import load_registry
from tools.vocabulary import errors as E
from tools.vocabulary.errors import RegistryInvalid

from _helpers import (ABSENT, CONSUMER_PATH, REAL_REGISTRY, REPO_ROOT, concept,
                      load, rejection, write_registry)

# ADR-0008 §2's table. The compiler deliberately does not hard-code these — the
# schema declares them — so this is where the shipped schema is pinned to the ADR.
ADR_KINDS = {"closed", "open", "tenant_defined", "free_text"}


@pytest.fixture(scope="module")
def registry():
    """The real, shipped registry — loaded once, through the real entry point."""
    return load_registry(REAL_REGISTRY, REPO_ROOT)


# ---------------------------------------------------------------------------
# 1. The shipped registry, and the guard against a vacuous pass
# ---------------------------------------------------------------------------

def test_the_shipped_registry_is_valid(registry):
    """The whole gate in one line: `domain-vocabulary/` compiles."""
    assert registry.concepts


def test_the_gate_actually_read_the_registry(registry):
    """Vacuity guard: a path-resolution bug must not turn this file into a
    suite that passes on an empty directory."""
    on_disk = sorted(path.name for path in (REAL_REGISTRY / "concepts").glob("*.yaml"))
    assert on_disk, "no domain files on disk — the glob or the path is wrong"
    assert sorted(registry.files) == on_disk, (
        f"compiler read {sorted(registry.files)} but {on_disk} is on disk"
    )
    # Named concepts it must have seen, the same shape as the boundary walker's
    # guard: a registry that loaded but lost half its content fails here.
    for expected in ("customer_billing_mode", "reason_code",
                     "grouping_field_value", "plan_name"):
        assert expected in registry.concepts, f"compiler did not see {expected}"


def test_the_schema_declares_exactly_the_four_kinds(registry):
    """ADR-0008 §2. A fifth kind is a decision, not an implementation detail."""
    assert set(registry.schema.kinds) == ADR_KINDS


def test_every_kind_is_represented(registry):
    """#198's tracer bullet carries one concept of each kind, so every branch of
    the shape rules is exercised by real data and not only by fixtures."""
    for kind in ADR_KINDS:
        assert registry.of_kind(kind), f"no concept of kind {kind!r}"


def test_declared_consumers_resolve_and_are_not_vacuous(registry):
    """Consumer resolution is enforced by loading, so this guards the other
    direction: a registry where nothing declared a consumer would pass the
    resolution rule without ever exercising it."""
    declared = [c for concept_ in registry.concepts.values() for c in concept_.consumers]
    assert len(declared) >= 4, "too few declared consumers to be exercising anything"
    for consumer in declared:
        assert (REPO_ROOT / consumer.path).exists()


def test_the_registry_enumerates_no_tenant_owned_value_set(registry):
    """Map #137 constraint 5, as a schema rule: UBB never ships a catalogue of
    the tenant's models, providers or grouping values. The schema forbids the
    fields; this asserts the shipped registry actually comes out that way."""
    for kind in ("tenant_defined", "free_text"):
        for concept_ in registry.of_kind(kind):
            assert concept_.declared_values == (), (
                f"{concept_.name} is {kind} but declares values"
            )


def test_retired_terms_are_registry_data(registry):
    """#206's forbidden-term sweep needs a declared input, not a list somebody
    maintains by memory. This is that input existing and being addressable."""
    retired = registry.retired_terms
    assert retired, "no retired terms declared"
    assert retired["meter_only"] == "customer_billing_mode"


# ---------------------------------------------------------------------------
# 2. Negative controls — one per named reason
# ---------------------------------------------------------------------------

def test_a_term_defined_twice_across_files_is_rejected(tmp_path):
    """AC: CI rejects a term defined twice across files."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
        "spend-controls.yaml": {"thing": concept()},
    })
    assert E.DUPLICATE_TERM in invalid.codes()
    assert any("economics.yaml" in error.message for error in invalid.errors)


def test_conflicting_definitions_across_files_are_rejected(tmp_path):
    """AC: CI rejects a term defined with conflicting definitions across files.

    Reported under its own code, not as a plain duplicate: two definitions that
    disagree is the failure that makes the registry stop being an oracle, and a
    reader should not have to diff two files to discover which one they have.
    """
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=["alpha", "beta"])},
        "spend-controls.yaml": {"thing": concept(values=["alpha", "gamma"])},
    })
    assert E.CONFLICTING_DEFINITION in invalid.codes()
    assert E.DUPLICATE_TERM not in invalid.codes()


def test_a_term_defined_twice_in_one_file_is_rejected(tmp_path):
    """The same fault YAML would otherwise hide: a repeated mapping key loads as
    one entry under `safe_load`, last one wins, and every later check passes."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": (
        "thing:\n"
        "  kind: closed\n"
        "  summary: The first definition.\n"
        "  values: [alpha]\n"
        "  label_key_prefix: thing\n"
        "  consumers: []\n"
        "thing:\n"
        "  kind: closed\n"
        "  summary: The second definition, which YAML would silently keep.\n"
        "  values: [beta]\n"
        "  label_key_prefix: thing\n"
        "  consumers: []\n"
    )})
    assert E.DUPLICATE_KEY in invalid.codes()


def test_an_undeclared_consumer_surface_is_rejected(tmp_path):
    """AC: CI rejects a concept whose declared consumer cannot be resolved."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        consumers=[{"surface": "mainframe", "path": CONSUMER_PATH}],
    )}})
    assert E.UNKNOWN_CONSUMER_SURFACE in invalid.codes()


def test_a_consumer_path_that_does_not_exist_is_rejected(tmp_path):
    """The other half of resolution: a surface that exists, pointed at a file
    that does not. A consumer resolving to nothing is a consumer nothing can
    ever be checked against."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        consumers=[{"surface": "backend", "path": "ubb-platform/apps/gone.py"}],
    )}})
    assert E.CONSUMER_PATH_MISSING in invalid.codes()


def test_a_consumer_path_outside_its_surface_is_rejected(tmp_path):
    """A real file, under the wrong surface. Without the root check, `console`
    could point at a backend module and the mislabelling would never surface."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        consumers=[{"surface": "console", "path": CONSUMER_PATH}],
    )}})
    assert E.CONSUMER_PATH_OUTSIDE_SURFACE in invalid.codes()


def test_a_consumer_escaping_the_repository_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        consumers=[{"surface": "backend", "path": "ubb-platform/../../etc/passwd"}],
    )}})
    assert E.CONSUMER_PATH_OUTSIDE_SURFACE in invalid.codes()


def test_a_malformed_consumer_entry_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        consumers=["ubb-platform/apps/example/models.py"],
    )}})
    assert E.CONSUMER_NOT_MAPPING in invalid.codes()


def test_an_unknown_kind_is_rejected(tmp_path):
    """The schema declares the kinds; anything else is a concept whose consumer
    obligation nobody has decided."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(kind="mostly_closed")},
    })
    assert E.UNKNOWN_KIND in invalid.codes()


def test_a_kind_missing_a_required_field_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=ABSENT)},
    })
    assert E.MISSING_FIELD in invalid.codes()


def test_a_concept_with_no_declared_consumers_key_is_rejected(tmp_path):
    """`consumers` is required even though it may be empty. An omitted key would
    be silently unchecked; `consumers: []` is a statement somebody made."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(consumers=ABSENT)},
    })
    assert E.MISSING_FIELD in invalid.codes()


def test_a_kind_carrying_a_forbidden_field_is_rejected(tmp_path):
    """A `tenant_defined` concept that enumerates values is the exact thing map
    #137 constraint 5 forbids — UBB acquiring the tenant's catalogue."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": {
        "kind": "tenant_defined",
        "summary": "A tenant-owned set that UBB has started enumerating.",
        "values": ["gpt_4", "claude_opus"],
        "consumers": [],
    }}})
    assert E.FORBIDDEN_FIELD in invalid.codes()


def test_an_unknown_field_is_rejected(tmp_path):
    """`value:` for `values:` must not produce a closed concept with no values."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        values=ABSENT, value=["alpha"],
    )}})
    assert E.UNKNOWN_FIELD in invalid.codes()
    assert E.MISSING_FIELD in invalid.codes()


def test_a_value_outside_the_token_pattern_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=["Alpha Beta"])},
    })
    assert E.INVALID_TOKEN in invalid.codes()


def test_a_concept_name_outside_the_token_pattern_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"Thing": concept()}})
    assert E.INVALID_TOKEN in invalid.codes()


def test_a_repeated_value_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=["alpha", "alpha"])},
    })
    assert E.DUPLICATE_VALUE in invalid.codes()


def test_an_empty_value_set_is_rejected(tmp_path):
    """A closed concept with no values is not a closed concept — it is a
    `tenant_defined` or `free_text` one that has not admitted it."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=[])},
    })
    assert E.EMPTY_VALUE_SET in invalid.codes()


def test_an_open_concept_that_refuses_unknown_values_is_rejected(tmp_path):
    """`open` means consumers accept values UBB has never seen. Declaring it
    open and then `allow_unknown: false` describes a closed concept."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": {
        "kind": "open",
        "summary": "Open in name only.",
        "known_values": ["alpha"],
        "allow_unknown": False,
        "label_key_prefix": "thing",
        "consumers": [],
    }}})
    assert E.OPEN_MUST_ALLOW_UNKNOWN in invalid.codes()


def test_a_term_both_retired_and_live_is_rejected(tmp_path):
    """The forbidden-term sweep works over text, so it cannot forbid a word here
    and require it there. Ambiguity is caught where it is authored."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(values=["alpha"],
                                            retired_aliases=["beta"])},
        "spend-controls.yaml": {"other": concept(values=["beta"],
                                                 label_key_prefix="other")},
    })
    assert E.RETIRED_ALIAS_COLLISION in invalid.codes()


def test_an_empty_schema_file_is_rejected(tmp_path):
    """An empty file parses to nothing, and "nothing" must not be mistaken for
    "no faults found" — every error the compiler raises names a reason."""
    invalid = rejection(tmp_path, schema="", concepts={
        "economics.yaml": {"thing": concept()},
    })
    assert E.SCHEMA_INVALID in invalid.codes()


def test_an_empty_domain_file_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": "# nothing here\n"})
    assert E.FILE_NOT_MAPPING in invalid.codes()


def test_a_registry_with_no_domain_files_is_rejected(tmp_path):
    """An empty registry would satisfy every consumer check vacuously."""
    invalid = rejection(tmp_path, concepts={})
    assert E.REGISTRY_EMPTY in invalid.codes()


def test_a_registry_directory_without_the_required_files_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={}, make_concepts_dir=False)
    assert E.REGISTRY_MISSING in invalid.codes()


def test_a_file_the_registry_would_not_carry_is_rejected(tmp_path):
    """A `webhooks.yml` in `concepts/` must not sit there contributing nothing
    while CI stays green — the same silent-omission shape as the unanchored
    `lib/` in `.gitignore` that dropped twenty-two modules for weeks."""
    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    (registry_dir / "concepts" / "webhooks.yml").write_text(
        "other: {}\n", encoding="utf-8")

    with pytest.raises(RegistryInvalid) as raised:
        load_registry(registry_dir, tmp_path)
    assert E.UNEXPECTED_FILE in raised.value.codes()


def test_a_domain_file_left_outside_the_concepts_directory_is_rejected(tmp_path):
    """The same silent-omission rule, at the registry's own root.

    A `webhooks.yaml` sitting beside `schema.yaml` looks exactly like registry
    content and is read by nothing. Closing the hole inside `concepts/` while
    leaving it open one level up would enforce the rule where it is easy to see
    and not where the file would actually land.
    """
    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    (registry_dir / "webhooks.yaml").write_text("other: {}\n", encoding="utf-8")

    with pytest.raises(RegistryInvalid) as raised:
        load_registry(registry_dir, tmp_path)
    assert E.UNEXPECTED_FILE in raised.value.codes()


def test_a_readme_beside_the_registry_is_not_registry_content(tmp_path):
    """The one exception, and the reason the shipped registry loads at all."""
    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    (registry_dir / "README.md").write_text("# notes\n", encoding="utf-8")

    assert load_registry(registry_dir, tmp_path).concepts


def test_a_concepts_path_that_is_a_file_is_rejected_by_name(tmp_path):
    """Every fault carries a code. `concepts/` as a file must not escape as a
    NotADirectoryError traceback from inside the compiler."""
    registry_dir = write_registry(tmp_path, concepts={}, make_concepts_dir=False)
    (registry_dir / "concepts").write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(RegistryInvalid) as raised:
        load_registry(registry_dir, tmp_path)
    assert E.REGISTRY_MISSING in raised.value.codes()


def test_one_term_retired_by_two_concepts_is_rejected(tmp_path):
    """`retired_terms` maps a term to what replaced it, so a second claim would
    silently win — the same last-one-wins default `loader.py` exists to abolish,
    in the very map #206's sweep consumes."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(retired_aliases=["old_word"])},
        "spend-controls.yaml": {"other": concept(label_key_prefix="other",
                                                 retired_aliases=["old_word"])},
    })
    assert E.DUPLICATE_RETIRED_ALIAS in invalid.codes()


def test_a_term_both_swept_and_sense_retired_is_rejected(tmp_path):
    """The two lists answer the same question differently, and the sweep can
    only be given one answer. `retired_aliases` says "forbidden wherever this
    word appears"; `retired_senses` says "forbidden in one sense, and here is
    the one that survives". Both about one word is a contradiction authored in
    two places, which is exactly what a single-registry load exists to catch."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(retired_aliases=["old_word"])},
        "spend-controls.yaml": {"other": concept(
            label_key_prefix="other",
            retired_senses=[{"term": "old_word",
                             "retired_as": "one sense.",
                             "survives_as": "another sense."}],
        )},
    })
    assert E.RETIRED_SENSE_CONFLICT in invalid.codes()


def test_one_term_sense_retired_by_two_concepts_is_rejected(tmp_path):
    """As with retired aliases: "which sense survives?" must have one answer,
    and a second claim would silently win the mapping."""
    sense = [{"term": "old_word", "retired_as": "a sense.",
              "survives_as": "another."}]
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(retired_senses=sense)},
        "spend-controls.yaml": {"other": concept(label_key_prefix="other",
                                                 retired_senses=sense)},
    })
    assert E.DUPLICATE_RETIRED_SENSE in invalid.codes()


def test_a_retired_sense_missing_the_surviving_sense_is_rejected(tmp_path):
    """Without `survives_as` the entry is a retired alias somebody left out of
    the sweep's input — which is the failure this field exists to prevent, not
    a shape it may take."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        retired_senses=[{"term": "old_word", "retired_as": "a sense."}],
    )}})
    assert E.INVALID_RETIRED_SENSE in invalid.codes()


def test_an_empty_retired_senses_list_is_rejected(tmp_path):
    """An empty list reads as "we considered this and found none", which is a
    claim; omitting the key is the honest way to say nothing about it."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(retired_senses=[])},
    })
    assert E.INVALID_RETIRED_SENSE in invalid.codes()


# --- value semantics --------------------------------------------------------

def semantics(cases, inputs=("wet",), summary="A rule, for the compiler."):
    return {"summary": summary, "inputs": list(inputs), "cases": cases}


def test_a_decision_rule_with_a_hole_is_rejected(tmp_path):
    """AC: the lower-bound rule is data, not prose — and data that answers three
    of four cases is decided by whichever consumer meets the fourth first."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics([
            {"when": {"wet": True}, "then": "alpha", "because": "It is wet."},
        ]),
    )}})
    assert E.VALUE_SEMANTICS_NOT_TOTAL in invalid.codes()


def test_a_decision_rule_that_answers_one_case_twice_is_rejected(tmp_path):
    """Two rows for one combination is a rule whose answer depends on which one
    a reader checks first — the ambiguity `>=` versus `>` produced in the
    ceiling statuses before #158 §12.3 settled it."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics([
            {"when": {"wet": "any"}, "then": "alpha", "because": "Always."},
            {"when": {"wet": True}, "then": "beta", "because": "Except wet."},
        ]),
    )}})
    assert E.VALUE_SEMANTICS_AMBIGUOUS in invalid.codes()


def test_a_decision_rule_answering_with_an_undeclared_value_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics([
            {"when": {"wet": "any"}, "then": "gamma", "because": "Always."},
        ]),
    )}})
    assert E.VALUE_SEMANTICS_UNKNOWN_RESULT in invalid.codes()


def test_a_decision_rule_case_omitting_an_input_is_rejected(tmp_path):
    """A missing key is a case nobody decided, not a wildcard. `any` is how a
    rule says "this input does not affect the answer", and it has to be
    written."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics(
            inputs=("wet", "cold"),
            cases=[{"when": {"wet": True}, "then": "alpha", "because": "Wet."}],
        ),
    )}})
    assert E.INVALID_VALUE_SEMANTICS in invalid.codes()
    assert E.VALUE_SEMANTICS_NOT_TOTAL not in invalid.codes()


def test_a_decision_rule_case_without_a_reason_is_rejected(tmp_path):
    """A row with no `because` is the prose this field replaces, minus the
    prose — and the reason is the half a reviewer can actually disagree with."""
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics([{"when": {"wet": "any"}, "then": "alpha"}]),
    )}})
    assert E.INVALID_VALUE_SEMANTICS in invalid.codes()


def test_a_decision_rule_on_a_tenant_owned_concept_is_rejected(tmp_path):
    """A rule resolves to one of the concept's own values, so declaring one on a
    kind that has none would be enumerating the tenant's set by the back door.

    One cause, one error: the forbidden field is the fault, and the rule's
    answers not being values it does not have is that same fault restated. The
    exact code set is asserted, because "contains FORBIDDEN_FIELD" would pass
    just as happily while the compiler reported both.
    """
    invalid = rejection(tmp_path, concepts={"economics.yaml": {"thing": {
        "kind": "tenant_defined",
        "summary": "The tenant owns these.",
        "value_semantics": semantics([
            {"when": {"wet": "any"}, "then": "alpha", "because": "Always."},
        ]),
        "consumers": [],
    }}})
    assert invalid.codes() == {E.FORBIDDEN_FIELD}


def test_an_unusable_consumers_file_is_blamed_before_the_concepts(tmp_path):
    """One cause, one error — the same rule the schema path already follows."""
    invalid = rejection(
        tmp_path,
        consumers={"version": 1},  # no `surfaces` table at all
        concepts={"economics.yaml": {"thing": concept()}},
    )
    assert invalid.codes() == {E.CONSUMERS_INVALID}


def test_a_boolean_schema_version_is_rejected(tmp_path):
    """`isinstance(True, int)` is true in Python, so a bare int check would
    compile a schema versioned `True`."""
    schema = yaml.safe_load(
        (REAL_REGISTRY / "schema.yaml").read_text(encoding="utf-8"))
    schema["version"] = True
    invalid = rejection(tmp_path, schema=schema, concepts={
        "economics.yaml": {"thing": concept()},
    })
    assert E.SCHEMA_INVALID in invalid.codes()


def test_a_registry_file_that_is_not_utf8_is_rejected_by_name(tmp_path):
    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    (registry_dir / "concepts" / "broken.yaml").write_bytes(b"thing: \xff\xfe\n")

    with pytest.raises(RegistryInvalid) as raised:
        load_registry(registry_dir, tmp_path)
    assert E.YAML_INVALID in raised.value.codes()


def test_unparseable_yaml_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": "thing: [unclosed\n"})
    assert E.YAML_INVALID in invalid.codes()


def test_a_domain_file_that_is_not_a_mapping_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={"economics.yaml": "- thing\n- other\n"})
    assert E.FILE_NOT_MAPPING in invalid.codes()


def test_a_blank_summary_is_rejected(tmp_path):
    """Every concept says what it means, in a sentence a human wrote."""
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(summary="   ")},
    })
    assert E.INVALID_FIELD_TYPE in invalid.codes()


def test_an_uncompilable_token_pattern_override_is_rejected(tmp_path):
    invalid = rejection(tmp_path, concepts={
        "economics.yaml": {"thing": concept(token_pattern="^[a-z")},
    })
    assert E.INVALID_TOKEN_PATTERN in invalid.codes()


def test_a_broken_schema_is_rejected_before_the_concepts_are_blamed(tmp_path):
    """One cause, one error. A schema with no kind table must not report itself
    as an unknown kind on every concept in the registry."""
    invalid = rejection(
        tmp_path,
        schema={"version": 1, "token_pattern": "^[a-z_]+$",
                "concept_fields": {"required": ["kind"], "optional": []},
                "kinds": {}},
        concepts={"economics.yaml": {"thing": concept()}},
    )
    assert invalid.codes() == {E.SCHEMA_INVALID}


def test_a_surface_whose_root_has_vanished_is_rejected_once(tmp_path):
    """One cause, one error — and the concepts naming it are told the truth.

    The surface stays registered despite the bad root, so a concept pointing at
    it is never told the surface is undeclared (it is), and its paths are not
    re-reported one by one under a cause already stated. Two concepts name the
    vanished surface here precisely so the cascade would show if it existed.
    """
    invalid = rejection(
        tmp_path,
        consumers={"version": 1, "surfaces": {
            "backend": {"summary": "The platform.", "root": "ubb-platform"},
            "moved": {"summary": "A directory that no longer exists.",
                      "root": "ubb-frontend"},
        }},
        surface_roots=["ubb-platform"],  # `ubb-frontend` deliberately absent
        concepts={"economics.yaml": {
            "thing": concept(consumers=[
                {"surface": "moved", "path": "ubb-frontend/one.ts"},
                {"surface": "moved", "path": "ubb-frontend/two.ts"},
            ]),
            "other": concept(label_key_prefix="other", consumers=[
                {"surface": "moved", "path": "ubb-frontend/three.ts"},
            ]),
        }},
    )
    assert invalid.codes() == {E.SURFACE_ROOT_MISSING}
    assert len(invalid.errors) == 1, [str(e) for e in invalid.errors]


# ---------------------------------------------------------------------------
# 3. Positive controls — the legal constructions that must keep passing
# ---------------------------------------------------------------------------

def test_a_concept_with_no_consumer_is_legal_and_named(tmp_path):
    """The rule that keeps the later checks non-vacuous: a concept nothing
    consumes yet is legal, but it is legal *visibly*."""
    registry = load(tmp_path, concepts={
        "economics.yaml": {"thing": concept(consumers=[])},
    })
    assert registry.concepts_without_consumers == ("thing",)


def test_a_tenant_defined_concept_declaring_no_values_is_legal(tmp_path):
    registry = load(tmp_path, concepts={"economics.yaml": {"thing": {
        "kind": "tenant_defined",
        "summary": "Values the tenant owns; UBB defines only the field.",
        "consumers": [{"surface": "backend", "path": CONSUMER_PATH}],
    }}})
    assert registry.concepts["thing"].declared_values == ()


def test_a_token_pattern_override_admits_a_structured_value(tmp_path):
    """The webhook catalogue's `<owner>.<past-tense>` names arrive with #202 and
    must not need a compiler change to be expressible."""
    registry = load(tmp_path, concepts={"economics.yaml": {"thing": concept(
        token_pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        values=["task.completed", "invoice.finalized"],
    )}})
    assert registry.concepts["thing"].values == ("task.completed", "invoice.finalized")


def test_a_total_unambiguous_decision_rule_loads(tmp_path):
    """The positive control the four rejections above need. Without it a
    compiler that refused every rule would pass all of them."""
    registry = load(tmp_path, concepts={"economics.yaml": {"thing": concept(
        value_semantics=semantics(
            inputs=("wet", "cold"),
            cases=[
                {"when": {"wet": True, "cold": "any"}, "then": "alpha",
                 "because": "Wet decides it, whatever the temperature."},
                {"when": {"wet": False, "cold": "any"}, "then": "beta",
                 "because": "Dry decides it, whatever the temperature."},
            ],
        ),
    )}})

    rule = registry.concepts["thing"].value_semantics
    assert rule.inputs == ("wet", "cold")
    assert [case.then for case in rule.cases] == ["alpha", "beta"]


def test_a_sense_retired_word_is_not_sweep_input(tmp_path):
    """The whole point of the second list: `retired_terms` is what #206 walks,
    and a word that survives in another sense must not be in it — while still
    being visible to a reader, and to the acceptance audit, by name."""
    registry = load(tmp_path, concepts={"economics.yaml": {"thing": concept(
        retired_aliases=["gone_everywhere"],
        retired_senses=[{"term": "gone_here_only",
                         "retired_as": "the sense that went.",
                         "survives_as": "the sense that stayed."}],
    )}})

    assert set(registry.retired_terms) == {"gone_everywhere"}
    concept_name, sense = registry.retired_senses["gone_here_only"]
    assert concept_name == "thing"
    assert sense.survives_as == "the sense that stayed."


def test_all_four_kinds_load_together(tmp_path):
    """Every branch of the shape rules, in one registry, off the real schema."""
    registry = load(tmp_path, concepts={"economics.yaml": {
        "a_closed": concept(),
        "an_open": {
            "kind": "open",
            "summary": "UBB knows some values; consumers accept others.",
            "known_values": ["alpha"],
            "allow_unknown": True,
            "label_key_prefix": "an_open",
            "consumers": [],
        },
        "a_tenant_set": {
            "kind": "tenant_defined",
            "summary": "The tenant owns these.",
            "consumers": [],
        },
        "some_prose": {
            "kind": "free_text",
            "summary": "Not vocabulary, and recorded as such.",
            "consumers": [],
        },
    }})
    assert {c.kind for c in registry.concepts.values()} == ADR_KINDS


# ---------------------------------------------------------------------------
# The CLI reports the same verdict a human can run
# ---------------------------------------------------------------------------

def test_the_cli_names_the_reason_and_exits_nonzero(tmp_path, capsys):
    """AC: the compiler reports, BY NAME, the reason an invalid registry fails.
    A gate whose output is "invalid" gives an author nothing to act on."""
    from tools.vocabulary.__main__ import main

    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept(kind="mostly_closed")},
    })
    status = main(["--registry", str(registry_dir), "--repo-root", str(tmp_path)])

    assert status == 1
    assert E.UNKNOWN_KIND in capsys.readouterr().err


def test_the_cli_reports_the_shipped_registry_as_valid(capsys):
    """Status 0 means BOTH halves of the CLI's verdict passed: the registry is
    valid and every artifact generated from it is current (#200). One command,
    one answer — so a stale artifact fails here too, and the generated-artifact
    gate lives in `test_generated_vocabulary.py`."""
    from tools.vocabulary.__main__ import main

    status = main(["--registry", str(REAL_REGISTRY), "--repo-root", str(REPO_ROOT)])

    assert status == 0
    output = capsys.readouterr().out
    assert "is valid" in output
    # The report names what nothing consumes yet — the visibility half of
    # "legal and visible" reaches a human, not just an attribute.
    assert "concepts with no declared consumer" in output
