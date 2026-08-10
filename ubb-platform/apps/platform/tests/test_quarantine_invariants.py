"""What a held name must never become (#265).

An unrecognised name is accepted, held and marked unresolved, and a tenant
decides what it meant. **Never auto-registered** is the fence that matters most
in that sentence: a typo must not be able to become permanent billing
vocabulary by arriving twice, because after it has there is no test that tells
it from a name somebody chose.

That fence does not fall over as a line of code somebody writes on purpose. It
falls over as a convenience — a ``get_or_create`` in the accept path, or a
foreign key from the held name to the declaration it was once mapped to, after
which the next arrival of the same typo resolves through it and no tenant
decides anything. All three rules below are that one failure, approached from
the three directions it can arrive from.

===============================  =============================================
``never-auto-register``          Nothing on the quarantine path writes a
                                 declaration. Registering is a tenant act, and
                                 this path is handed the result of one.
``quarantine-holds-no-``         A held name never POINTS at a declaration —
``declaration``                  not by relation and not by bare identity. It
                                 may record a declared KEY, which resolves to
                                 nothing on its own; a pointer is the
                                 auto-registration path rebuilt as a graph.
``nothing-declares-from-``       And nothing in the catalogue points back. A
``quarantine``                   declaration carrying "the typo I came from"
                                 makes the held name part of the vocabulary's
                                 provenance, reachable from the same direction.
===============================  =============================================

**The obligations** (``tests/contracts/README.md``): every rule has a negative
control pushing a synthetic violation through the real classifier, every
allowance has a positive control, and every walk has a vacuity guard — a check
over an absence that silently read nothing is worse than no check at all.

**What this cannot see**, stated rather than left to be discovered. The write
rule is syntactic: ``target = EventType`` on one line and ``target.objects
.create(...)`` on the next is dataflow, and it is the same limit the gate in
``test_event_type_satellite_invariants.py`` records for local aliasing. The
shortcut is caught where it is written, not where it is laundered. What
narrows the exposure is that the module the rule is stated over is small,
single-purpose, and read by anyone changing this behaviour.
"""
import ast
import textwrap
from pathlib import Path

from django.db import models
from django.test.utils import isolate_apps

from apps.platform.event_types.models import (
    EventType,
    Measurement,
    QuarantinedKey,
)
# One definition of each of these, shared with the gates next door rather than
# copied: two encodings of one fact drift, and the one that drifts is the one
# nobody is looking at.
from apps.platform.tests.test_event_type_satellite_invariants import (
    _dotted_name,
    _local_fields,
    field_words,
    model_label,
    site_of,
)
from apps.platform.tests.test_model_naming import first_party_models

# apps/platform/tests/test_quarantine_invariants.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

TICKET = "#265"

RULE_REGISTER = "never-auto-register"
RULE_HOLDS = "quarantine-holds-no-declaration"
RULE_DECLARES = "nothing-declares-from-quarantine"

#: The modules that handle an unrecognised name. Spelled as an explicit list so
#: that a second one joining the path is a line somebody writes rather than a
#: rule that quietly stopped covering the code it was about.
QUARANTINE_PATH = ("apps/platform/event_types/quarantine.py",)

#: The records a tenant declares. Writing one of these from the quarantine path
#: IS auto-registration, whatever the surrounding code believes it is doing.
DECLARATION_CLASSES = frozenset({"EventType", "Measurement"})
DECLARATION_MODELS = (EventType, Measurement)

#: Every way Django writes a row. The async spellings are here because they are
#: the same act, and a rule that listed only the familiar half would be a rule
#: with a documented way round it.
WRITE_METHODS = frozenset({
    "create", "acreate", "get_or_create", "aget_or_create",
    "update_or_create", "aupdate_or_create", "bulk_create", "abulk_create",
    "save", "asave", "update", "aupdate",
})

#: A declaration held as an identity rather than as a relation — the evasion
#: that passes every check that walks a relation, because there is nothing to
#: walk. #261 found this shape for the supplier and #264 for the analytics
#: grouping; it is closed here in the same commit as the rule it evades rather
#: than found a third time.
#:
#: The tenant's own KEYS are deliberately absent: ``event_type_key`` and
#: ``resolved_key`` are names a tenant chose, they resolve to nothing on their
#: own, and holding them is the design (see ``QuarantinedKey.resolved_key``).
#: What is refused is a surrogate identity, which is a pointer wearing a
#: column's clothes.
DECLARATION_IDENTIFIER_NAMES = frozenset({
    "event_type_id", "event_type_uuid", "event_type_ref",
    "measurement_id", "measurement_uuid", "measurement_ref",
    "declaration_id", "declaration_uuid", "declaration_ref",
    "resolved_event_type_id", "resolved_measurement_id",
    "resolved_declaration_id",
})

#: And the same evasion pointing the other way.
QUARANTINE_IDENTIFIER_NAMES = frozenset({
    "quarantined_key_id", "quarantined_key_uuid", "quarantined_key_ref",
    "quarantine_id", "quarantine_uuid", "quarantine_ref",
    "held_name_id", "unrecognised_id",
})

#: What a held name is allowed to relate to. The tenant, and nothing else: it
#: is a record of something that arrived, and every other relation available to
#: it points into the catalogue.
QUARANTINE_MAY_RELATE_TO = frozenset({"tenant"})


# ---------------------------------------------------------------------------
# never-auto-register — the source of the quarantine path
# ---------------------------------------------------------------------------

def classify_declaration_write(label, tree):
    """Every declaration write in one module, and how many calls were read.

    Returns ``(hits, calls)``. The second number is the vacuity guard's input:
    a classifier handed an empty tree finds no violations and proves nothing,
    which is indistinguishable from a clean module unless the count is checked.

    Two shapes, and the second is the one that reads as innocent. A construction
    — ``EventType(...)`` — is obviously making a declaration. A manager write —
    ``Measurement.objects.get_or_create(...)`` — reads as "make sure it is
    there", which is the sentence auto-registration arrives in.
    """
    hits, calls = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        calls += 1
        segments = _dotted_name(node.func).split(".")
        if not segments:
            continue

        if len(segments) == 1 and segments[0] in DECLARATION_CLASSES:
            how = f"constructs a {segments[0]}"
        elif (segments[-1] in WRITE_METHODS
              and set(segments[:-1]) & DECLARATION_CLASSES):
            how = f"writes a declaration via {'.'.join(segments)}"
        else:
            continue

        hits.append((
            RULE_REGISTER, label,
            f"{label} {how}. Nothing on the quarantine path may register a "
            f"name ({TICKET}): a misspelling that arrives twice would become "
            f"declared billing vocabulary — on an invoice, under a name nobody "
            f"chose — and afterwards there is no test that tells it from a "
            f"real one. Registration is a TENANT act; this path is handed the "
            f"declaration and records that it happened",
        ))
    return hits, calls


def _walk_the_quarantine_path():
    hits, calls, read = [], 0, []
    for label in QUARANTINE_PATH:
        source = (PLATFORM_ROOT / label).read_text(encoding="utf-8")
        module_hits, module_calls = classify_declaration_write(
            label, ast.parse(source))
        hits.extend(module_hits)
        calls += module_calls
        read.append(label)
    return hits, calls, read


_SOURCE_HITS, _CALLS_READ, _MODULES_READ = _walk_the_quarantine_path()


def test_the_source_walk_actually_read_the_quarantine_path():
    """Vacuity guard: an absence found in an empty tree is not an absence."""
    assert list(_MODULES_READ) == list(QUARANTINE_PATH)
    assert _CALLS_READ > 20, f"only classified {_CALLS_READ} calls"


def test_nothing_on_the_quarantine_path_registers_a_declaration():
    failures = "\n".join(message for _, _, message in _SOURCE_HITS)
    assert not failures, "\n" + failures


def _classify_source(source):
    """A synthetic module through the real entry point."""
    return classify_declaration_write("synthetic.py",
                                      ast.parse(textwrap.dedent(source)))[0]


def test_negative_control_a_get_or_create_on_the_accept_path_is_flagged():
    """The sentence auto-registration actually arrives in.

    Nobody writes "register the typo". They write "make sure the Event Type
    exists", in the accept path, where the alternative appears to be losing the
    event — and the fence is gone.
    """
    hits = _classify_source("""
        def hold(tenant, key):
            declared, _ = EventType.objects.get_or_create(tenant=tenant, key=key)
            return declared
    """)
    assert len(hits) == 1 and hits[0][0] == RULE_REGISTER


def test_negative_control_constructing_a_declaration_is_flagged():
    hits = _classify_source("""
        def hold(event_type, code):
            Measurement(event_type=event_type, code=code).save()
    """)
    assert hits and hits[0][0] == RULE_REGISTER


def test_negative_control_the_async_spelling_is_flagged_too():
    """A rule listing only the familiar half is a rule with a way round it."""
    hits = _classify_source("""
        async def hold(tenant, key):
            await EventType.objects.aget_or_create(tenant=tenant, key=key)
    """)
    assert hits and hits[0][0] == RULE_REGISTER


def test_negative_control_a_bulk_write_is_flagged():
    """The batch repair screen, which is where "however many times" bites."""
    hits = _classify_source("""
        def sweep_up(rows):
            Measurement.objects.bulk_create(rows)
    """)
    assert hits and hits[0][0] == RULE_REGISTER


def test_positive_control_reading_a_declaration_is_not_writing_one():
    """The allowance branch — the half the rule is useless without.

    The quarantine path must be able to check that the declaration it was
    handed is the right kind, belongs to this tenant and sits beneath the right
    Event Type. A rule that flagged those would have to be switched off to
    build any of the three remediation paths.
    """
    hits = _classify_source("""
        def target(held, declaration):
            if not isinstance(declaration, EventType):
                raise WrongDeclaration(Measurement.__name__)
            if declaration.tenant_id != held.tenant_id:
                raise NotThisTenants(declaration.key)
            QuarantinedKey.objects.filter(pk=held.pk).update(resolved_key=declaration.key)
            return declaration.key
    """)
    assert hits == []


def test_the_real_module_is_the_subject_of_this_rule():
    """The rule has to be about a module that names these classes.

    A quarantine path that stopped importing the declarations entirely would
    pass the walk above for the wrong reason — vacuously — and this is what
    tells the two apart.
    """
    source = (PLATFORM_ROOT / QUARANTINE_PATH[0]).read_text(encoding="utf-8")
    named = {segment
             for node in ast.walk(ast.parse(source))
             if isinstance(node, (ast.Name, ast.Attribute))
             for segment in _dotted_name(node).split(".")}
    assert DECLARATION_CLASSES <= named


# ---------------------------------------------------------------------------
# The model registry — the held name and the catalogue point at each other in
# neither direction
# ---------------------------------------------------------------------------

#: The subject, by LABEL rather than by class identity — for #262's reason: a
#: synthetic control has to be able to carry the real record's identity, or the
#: rules below are the ones nothing ever exercises.
HELD_NAME_LABEL = model_label(QuarantinedKey)


def classify_quarantine_reach(model, field):
    """``quarantine-holds-no-declaration`` — outbound, relation or identity."""
    if model_label(model) != HELD_NAME_LABEL:
        return None
    if field.is_relation:
        if field.related_model in DECLARATION_MODELS:
            why = f"relates to {field.related_model.__name__}"
        elif field.name in QUARANTINE_MAY_RELATE_TO:
            return None
        else:
            why = f"relates to {field.related_model.__name__}, which is not " \
                  f"one of {sorted(QUARANTINE_MAY_RELATE_TO)}"
    elif field.name in DECLARATION_IDENTIFIER_NAMES:
        why = "holds a declaration's identity without holding the declaration"
    else:
        return None
    return (
        RULE_HOLDS, site_of(model, field),
        f"{site_of(model, field)} {why}. A held name never POINTS at a "
        f"declaration ({TICKET}): once a held typo points at one, the next "
        f"event carrying that typo can be resolved through it without a tenant "
        f"deciding anything — which is auto-registration arriving as a foreign "
        f"key nobody thought was about that. It would also let a two-year-old "
        f"quarantine row refuse a declaration's deletion on behalf of a "
        f"misspelling. What it may record is the declared KEY, which resolves "
        f"to nothing on its own",
    )


def classify_declaring_from_quarantine(model, field):
    """``nothing-declares-from-quarantine`` — inbound, relation or identity."""
    if field.is_relation and field.related_model is QuarantinedKey:
        why = "holds a QuarantinedKey"
    elif not field.is_relation and field.name in QUARANTINE_IDENTIFIER_NAMES:
        why = "holds a held name's identity without holding the record"
    else:
        return None
    return (
        RULE_DECLARES, site_of(model, field),
        f"{site_of(model, field)} {why}. Nothing points back at a held name "
        f"({TICKET}). A declaration carrying the typo it came from makes the "
        f"held name part of the vocabulary's provenance, and the next arrival "
        f"of that typo is then one join away from resolving itself. Quarantine "
        f"records what a tenant DECIDED; it is never a route into the "
        f"catalogue",
    )


def _walk_registry():
    hits, seen, fields_seen = [], set(), 0
    for model in first_party_models():
        seen.add(model_label(model))
        for field in _local_fields(model):
            fields_seen += 1
            hits.extend(filter(None, [
                classify_quarantine_reach(model, field),
                classify_declaring_from_quarantine(model, field),
            ]))
    return hits, seen, fields_seen


_REGISTRY_HITS, _MODELS_SEEN, _FIELDS_SEEN = _walk_registry()


def _registry_failures(rule):
    return "\n".join(message for name, _, message in _REGISTRY_HITS
                     if name == rule)


def test_the_registry_walk_actually_saw_the_held_name():
    """Vacuity guard: both rules below are absences.

    The held name by name, because it is the subject; the two declarations
    because they are what the rules are stated AGAINST, and a walk that could
    not see them could not tell a relation to one from a relation to anything.
    """
    assert len(_MODELS_SEEN) > 50, f"only walked {len(_MODELS_SEEN)} models"
    for expected in ("event_types.QuarantinedKey", "event_types.EventType",
                     "event_types.Measurement", "usage.UsageEvent"):
        assert expected in _MODELS_SEEN, f"the walk did not visit {expected}"
    assert _FIELDS_SEEN > 300, f"only classified {_FIELDS_SEEN} fields"
    assert len(_local_fields(QuarantinedKey)) >= 10, (
        "the held name's own fields were not read")


def test_a_held_name_points_at_no_declaration():
    failures = _registry_failures(RULE_HOLDS)
    assert not failures, "\n" + failures


def test_nothing_in_the_catalogue_points_back_at_a_held_name():
    failures = _registry_failures(RULE_DECLARES)
    assert not failures, "\n" + failures


CATALOGUE_APP = "apps.platform.event_types"
CATALOGUE_LABEL = "event_types"


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_resolution_foreign_key_is_flagged():
    """The tidiest version of the mistake, and the one review would pass.

    "The held name resolved to this declaration — model it" is a sentence with
    nothing obviously wrong in it. What it builds is a lookup table from
    misspellings to declarations, which is the auto-registration this whole
    record refuses, arrived at from a modelling instinct.
    """
    class QuarantinedKey(models.Model):
        resolved_to = models.ForeignKey(EventType, null=True, blank=True,
                                        on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_quarantine_reach(
        QuarantinedKey, QuarantinedKey._meta.get_field("resolved_to"))
    assert hit is not None and hit[0] == RULE_HOLDS
    assert "EventType" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_bare_declaration_identifier_is_flagged():
    """The reach with nothing to walk — closed in the same commit as the rule
    it evades, rather than found a third time (#261, #264)."""
    class QuarantinedKey(models.Model):
        resolved_event_type_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_quarantine_reach(
        QuarantinedKey,
        QuarantinedKey._meta.get_field("resolved_event_type_id"))
    assert hit is not None and hit[0] == RULE_HOLDS


@isolate_apps(CATALOGUE_APP)
def test_negative_control_any_other_relation_on_the_held_name_is_flagged():
    """Stated as an allowlist, so a relation nobody anticipated is still a hit.

    Every relation available to this record other than its tenant points into
    the catalogue, directly or one hop away — a Provider, a grouping, a rate.
    A rule listing the two classes it could think of would miss the third.
    """
    class QuarantinedKey(models.Model):
        suggested_by = models.ForeignKey(Measurement, null=True, blank=True,
                                         on_delete=models.SET_NULL,
                                         related_name="+")

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_quarantine_reach(
        QuarantinedKey, QuarantinedKey._meta.get_field("suggested_by"))
    assert hit is not None and hit[0] == RULE_HOLDS


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_shape_that_shipped_is_allowed():
    """The allowance branch, exercised.

    A rule that flagged the tenant relation or the two keys would make this
    record unbuildable, and the registry walk would say so — identically to a
    walk that had simply gone wrong. The synthetic model carries the real one's
    label, so this reaches the allowance rather than passing for want of
    recognising the class (#262 shipped the other spelling and review caught
    it).
    """
    class QuarantinedKey(models.Model):
        tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                                   related_name="+")
        event_type_key = models.CharField(max_length=100)
        resolved_key = models.CharField(max_length=100, blank=True, default="")

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(QuarantinedKey) == HELD_NAME_LABEL, (
        "the control has to carry the real record's identity")
    assert [classify_quarantine_reach(QuarantinedKey, field)
            for field in _local_fields(QuarantinedKey)] == [None] * 4


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_declaration_remembering_its_typo_is_flagged():
    """The inbound direction, in the words somebody would use for it.

    "Which held name did this declaration come from" is a reasonable question
    and a reasonable column. It is also the provenance link that makes the next
    arrival of that typo resolvable without anyone deciding.
    """
    class EventType(models.Model):
        born_from = models.ForeignKey(QuarantinedKey, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name="+")

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_declaring_from_quarantine(
        EventType, EventType._meta.get_field("born_from"))
    assert hit is not None and hit[0] == RULE_DECLARES


@isolate_apps(CATALOGUE_APP)
def test_negative_control_the_inbound_bare_identifier_is_flagged_too():
    """Both directions get the identity twin, not just the one that was found
    first."""
    class Measurement(models.Model):
        quarantined_key_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_declaring_from_quarantine(
        Measurement, Measurement._meta.get_field("quarantined_key_id"))
    assert hit is not None and hit[0] == RULE_DECLARES


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_real_foreign_key_is_not_a_bare_identifier():
    """The rule must not fire on a shape it is asking for.

    Django gives the tenant relation an ``attname`` of ``tenant_id``, and a
    check reading attnames rather than field names is how a gate ends up
    failing the very column it wanted — after which it gets weakened until it
    stops meaning anything.
    """
    class QuarantinedKey(models.Model):
        tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                                   related_name="+")

        class Meta:
            app_label = CATALOGUE_LABEL

    field = QuarantinedKey._meta.get_field("tenant")
    assert "tenant" in field_words(field.attname), (
        "the control is only meaningful while the attname derives from the name")
    assert classify_quarantine_reach(QuarantinedKey, field) is None
    assert classify_declaring_from_quarantine(QuarantinedKey, field) is None
