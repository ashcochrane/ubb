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
rule resolves local aliases to a fixpoint — it has to, because the real module
reaches its declaration classes through a mapping and the rule would otherwise
be blind to its own subject — but one shape is still outside it: a declaration
arriving as a PARAMETER. ``register_the_held_name(held, declaration)`` calling
``declaration.save()`` names nothing this walker can tie to a class, and no
syntactic rule can, because the whole design of that function is to be handed a
declaration somebody else made.

That gap is closed behaviourally instead, and completely:
``test_quarantine.py`` counts the declaration rows and re-reads their lifecycle
either side of all three remediation paths, so a write through a parameter, an
alias or anything else fails there whatever it is spelled. The division is
deliberate — the source rule catches the shape at the line it is written, and
the behavioural test catches the effect however it was reached.
"""
import ast
import re
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

#: Every column the held name carries, by name. An ALLOWLIST rather than a list
#: of forbidden spellings, and the difference is the whole strength of the
#: rule: a denylist of ``event_type_id``, ``declaration_ref`` and whatever else
#: occurred to its author is walked past by ``resolves_to_id``, ``declared_pk``
#: or ``origin_typo_id``, none of which anybody would think to list.
#:
#: This record has a fixed and small column set, so the total form is available
#: — which the rules stated over the whole tree below cannot be. A new column
#: here is a line somebody writes, exactly as ``SATELLITE_HOLDERS`` and
#: ``DECLARATION_PARTS`` next door demand, and the refusal says so rather than
#: claiming the column is necessarily a pointer.
#:
#: The tenant's own KEYS are on the list on purpose: ``event_type_key`` and
#: ``resolved_key`` are names a tenant chose, they resolve to nothing on their
#: own, and holding them is the design (see ``QuarantinedKey.resolved_key``).
#: What has no line is a surrogate identity — a pointer wearing a column's
#: clothes.
HELD_NAME_COLUMNS = frozenset({
    "id", "created_at", "updated_at",
    "unrecognised", "tenant", "event_type_key", "measurement_key",
    "quantity", "quantities", "occurred_at",
    "resolution", "resolved_at", "resolved_key",
})

#: The same evasion pointing the other way, and here only a pattern is
#: available: the rule is stated over every model in the tree, so there is no
#: fixed column set to enumerate. Matched as whole name segments — a stem that
#: names this record, alone or qualified — which catches ``quarantine_pk`` and
#: ``quarantined_key_ref`` without needing either to have been imagined.
QUARANTINE_IDENTIFIER = re.compile(
    r"^(quarantine|quarantined|quarantined_key|held_name)(_[a-z0-9_]+)?$")

#: What a held name is allowed to relate to. The tenant, and nothing else: it
#: is a record of something that arrived, and every other relation available to
#: it points into the catalogue.
QUARANTINE_MAY_RELATE_TO = frozenset({"tenant"})


# ---------------------------------------------------------------------------
# never-auto-register — the source of the quarantine path
# ---------------------------------------------------------------------------

def declaration_names(tree):
    """Every local name in a module that could BE a declaration class.

    The classes themselves, plus anything assigned from an expression that
    mentions one, to a fixpoint. This is not decoration: the real module holds
    ``RESOLVES_TO = {...: EventType, ...: Measurement}`` and then
    ``expected = RESOLVES_TO[held.unrecognised]``, so ``expected.objects
    .create(...)`` is a shipped alias for both declarations and a rule matching
    only the class names would walk straight past it.

    Deliberately generous — a name that merely *touches* a declaration class
    counts. The cost of a false positive here is one line in a test explaining
    why a write is legal; the cost of a false negative is a typo becoming
    billing vocabulary.
    """
    assignments = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        bound = {t.id for t in targets if isinstance(t, ast.Name)}
        if node.value is None or not bound:
            continue
        mentions = {segment
                    for inner in ast.walk(node.value)
                    if isinstance(inner, (ast.Name, ast.Attribute))
                    for segment in _dotted_name(inner).split(".")}
        assignments.append((bound, mentions))

    names = set(DECLARATION_CLASSES)
    grew = True
    while grew:
        grew = False
        for bound, mentions in assignments:
            if mentions & names and not bound <= names:
                names |= bound
                grew = True
    return names


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
    subjects = declaration_names(tree)
    hits, calls = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        calls += 1
        segments = _dotted_name(node.func).split(".")
        if not segments:
            continue

        if len(segments) == 1 and segments[0] in subjects:
            how = f"constructs a declaration via {segments[0]}"
        elif segments[-1] in WRITE_METHODS and set(segments[:-1]) & subjects:
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


def test_negative_control_a_write_through_an_alias_is_flagged():
    """The escape that is a SHIPPED shape in the module under this rule.

    ``RESOLVES_TO`` maps each kind of held name to the class that answers it,
    and ``expected`` is that class. A rule matching only ``EventType`` and
    ``Measurement`` reads this as a write to something called "expected" and
    says nothing — while the line registers whichever declaration the held
    name happens to be about.
    """
    hits = _classify_source("""
        RESOLVES_TO = {"event_type": EventType, "measurement_key": Measurement}

        def hold(held, tenant, key):
            expected = RESOLVES_TO[held.unrecognised]
            return expected.objects.create(tenant=tenant, key=key)
    """)
    assert hits and hits[0][0] == RULE_REGISTER
    assert "expected.objects.create" in hits[0][2]


def test_negative_control_a_one_line_alias_is_flagged():
    """The plainest form of the same laundering."""
    hits = _classify_source("""
        def hold(tenant, key):
            target = Measurement
            target.objects.get_or_create(code=key)
    """)
    assert hits and hits[0][0] == RULE_REGISTER


def test_the_alias_resolver_reaches_the_real_module_s_own_indirection():
    """The fixpoint, exercised against the shipped source rather than a fixture.

    ``declaration_names`` is only worth having if it actually resolves the
    indirection this module ships. A test over synthetic source alone would
    pass identically if the real module had been rewritten to route its
    classes through something the resolver cannot follow.
    """
    source = (PLATFORM_ROOT / QUARANTINE_PATH[0]).read_text(encoding="utf-8")
    names = declaration_names(ast.parse(source))

    assert DECLARATION_CLASSES <= names
    assert {"RESOLVES_TO", "expected"} <= names, (
        "the module's own route to its declaration classes is not resolved, "
        f"so a write through it would go unseen — resolved: {sorted(names)}")


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
    elif field.name not in HELD_NAME_COLUMNS:
        why = (f"is a column nothing has declared. If it holds a declaration's "
               f"identity it is the evasion below; if it does not, add it to "
               f"`HELD_NAME_COLUMNS`")
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
    elif not field.is_relation and QUARANTINE_IDENTIFIER.match(field.name):
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
                     "event_types.Measurement", "usage.Posting"):
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
def test_negative_control_an_identifier_nobody_would_have_listed_is_flagged():
    """Why the outbound rule is an allowlist.

    ``resolves_to_id`` names no class, no app and none of the words a list of
    forbidden spellings would have been built from. It is still a pointer, and
    on an allowlist it does not have to have been imagined to be caught.
    """
    class QuarantinedKey(models.Model):
        resolves_to_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_quarantine_reach(
        QuarantinedKey, QuarantinedKey._meta.get_field("resolves_to_id"))
    assert hit is not None and hit[0] == RULE_HOLDS
    assert "HELD_NAME_COLUMNS" in hit[2], (
        "the refusal has to say what to do when the column is legitimate")


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
        quarantine_pk = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hits = [classify_declaring_from_quarantine(Measurement, field)
            for field in _local_fields(Measurement)
            if field.name != "id"]
    assert all(hit is not None and hit[0] == RULE_DECLARES for hit in hits)
    assert len(hits) == 2, (
        "the second spelling is here because the rule is a pattern rather "
        "than a list — `quarantine_pk` is one nobody would have enumerated")


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
