"""The two optional satellites, and the four things they must never become (#261).

``Provider`` and ``EventCategory`` are the most likely thing in slice 2 to be
over-built, so their limits are enforced here rather than described in a
docstring. Every claim below is a property of the *tree* — of the model registry
or of the source — which is why none of it lives beside the row-level tests in
``apps/platform/event_types/tests/test_models.py``.

Five rules, each a pure function, each shown to bite:

===========================  =================================================
``optional-satellite``       An Event Type may hold each satellite, and must
                             never require one. Internal work with no supplier
                             is a normal declaration, not an incomplete one.
``no-record-beneath``        Nothing but the Event Type holds a Provider. The
                             account-level record beneath the supplier was
                             removed from the model by a later decision, and
                             reading only the originating one would resurrect
                             it.
``category-stays-small``     One level, no hierarchy, no effective-dating. The
                             dating the originating decision required was
                             retired when the category left the pricing ladder
                             and became analytics-only.
``never-monetary``           Neither satellite carries money, and no rating,
                             cost-resolution or spend-ceiling module queries a
                             catalogue record. Slice 3 wired the cost
                             declaration into rating (#320) and reads it
                             through one function that answers in plain data;
                             the classes themselves stay out of reach.
``identity-not-spelling``    Supplier cost resolution keys on the Provider's
                             identity. No code path parses a supplier's name
                             out of an Event Type key, and the catalogue names
                             no supplier as a string.
===========================  =================================================

**The allowlist named its model before the model existed.** ``SATELLITE_HOLDERS``
carried ``event_types.EventType`` for a ticket before the record arrived (#262),
which is what makes ``no-record-beneath`` a gate rather than a note: the second
model to hold a Provider fails on arrival, whatever it is called, instead of
being argued about after it is built. The Event Type's own limits — no grouping
axis, no cost amount, one response shape, no relation between two of them — are
next door in ``test_event_type_declaration_invariants.py``.

**The obligations** (``tests/contracts/README.md``, from the boundary walker
next door): every rule has a negative control that pushes a synthetic violation
through the real entry point, and every walk has a vacuity guard, because a
check over an absence that silently read nothing is worse than no check at all.

**What these walkers cannot see**, stated rather than left to be discovered,
because ADR-0008 §9's rule is that a green board proves the declared invariants
passed and not that the declarations were worth making:

* **Local aliasing.** ``key = event_type.key`` followed by ``key.split("/")``
  two lines later is dataflow, and the walker is syntactic. The shortcut is
  caught where it is written, not where it is laundered.
* **Reaching a satellite through the Event Type.** Once the foreign keys land,
  ``posting.event_type.provider_id`` inside a rating service names neither the
  app nor the class, and no token check can see it. What catches that is the
  ordinary import matrix plus review; what this file catches is a behavioural
  module that reaches for the catalogue directly. The same is true of
  ``posting.measurement.concept`` (#264), which is the shortest route from a
  rating path to the opt-in grouping and names none of the tokens below.
"""
import ast
import re
from pathlib import Path

from django.db import models
from django.test.utils import isolate_apps

from apps.platform.event_types.models import EventCategory, Provider
# One definition of "every model a UBB app declares", shared with the gate next
# door rather than copied: two encodings of that fact could drift, and the one
# that drifted would be the one nobody was looking at.
from apps.platform.tests.test_model_naming import first_party_models

# apps/platform/tests/test_event_type_satellite_invariants.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

TICKET = "#261"
CATALOGUE_APP = "apps.platform.event_types"

RULE_OPTIONAL = "optional-satellite"
RULE_BENEATH = "no-record-beneath"
RULE_SMALL = "category-stays-small"
RULE_MONETARY = "never-monetary"
RULE_IDENTITY = "identity-not-spelling"

#: The models that may hold a satellite. The Event Type is the aggregate root
#: both hang off, and it is the only thing that may reach either.
SATELLITE_HOLDERS = frozenset({"event_types.EventType"})

#: A hierarchy is an adjacency list, a materialised path or a nested set. All
#: three announce themselves in a field name, so all three are refused by one
#: list rather than by three shapes of graph analysis.
HIERARCHY_FIELD_NAMES = frozenset({
    "parent", "parent_key", "parent_category", "ancestor",
    "path", "lft", "rght", "tree_id", "level", "depth",
})

#: Effective-dating and its close cousin, row versioning. ``created_at`` and
#: ``updated_at`` are row stamps rather than a validity interval and are not
#: here on purpose: they say when this row was written, never which row was in
#: force on a date, and reproducing a past answer is the requirement that was
#: retired.
DATING_FIELD_NAMES = frozenset({
    "effective_from", "effective_to", "effective_at", "effective_date",
    "valid_from", "valid_to", "as_of", "superseded_at", "superseded_by",
    "version", "revision", "generation",
})

#: Words that make a field a money field. ``_micros`` is the repository's money
#: suffix (ADR-0006 §1); the rest are the shapes a cost or a price takes when it
#: is not spelled in micros.
MONETARY_FIELD_WORDS = frozenset({
    "micros", "amount", "price", "cost", "currency", "fee", "markup", "rate",
})
MONETARY_FIELD_TYPES = frozenset({"DecimalField", "FloatField"})

#: A supplier named as a value rather than held as a relation. A bare
#: ``provider_id`` column is in the list on purpose: it is the most natural
#: evasion of every rule here at once, because it holds an identity while
#: declaring no relation, so nothing walks it and nothing constrains it.
#:
#: The usage row still carries the free-text shape and is deliberately out of
#: scope: it is the world slice 2 replaces, and the posting split owns its
#: removal. The rule is about the catalogue, which is being built now and has
#: no excuse.
STRINGLY_TYPED_SUPPLIER_NAMES = frozenset({
    "provider", "provider_key", "provider_name", "provider_slug",
    "provider_id", "provider_uuid", "provider_ref",
    "supplier", "supplier_key", "supplier_name", "supplier_slug",
    "supplier_id", "supplier_uuid", "supplier_ref",
    "vendor", "vendor_key", "vendor_name", "vendor_id",
})

#: Where a cost, a price or a spend ceiling is decided. If a satellite is
#: reachable from any of these, "nothing behavioural is wired" is false. Both
#: products entire rather than the modules that look relevant: metering's read
#: contract and its outbox handlers decide money too, and naming subdirectories
#: would have left them out for no reason a reader could reconstruct.
BEHAVIOURAL_SURFACES = (
    "apps/metering",   # rating, rate selection, the posting and its read contract
    "apps/billing",    # drawdown, invoicing and the spend ceilings
    "core/money.py",   # the money primitives themselves
)

#: What reaching the catalogue looks like from another module: its app label,
#: however it is spelled, or any of its classes by name. ``EventType`` joined
#: the list with the record (#262) — nothing behavioural may read the
#: declaration either, and the aggregate root is the name a rating path would
#: reach for first. ``MeasurementConcept`` joined it in #264, where the reach
#: is not merely unwired but forbidden outright: the grouping is analytics-only
#: and a rating path that can see it has made an analytics heading into a
#: costing input.
#:
#: What that last one catches is a module that NAMES the class — an import, an
#: ``apps.get_model``, a queryset. It does not catch ``posting.measurement
#: .concept``, which is now the shortest route to the grouping from a rating
#: path and names none of these tokens. That is the same limit the docstring
#: records for reaching a satellite through the Event Type, and it is stated
#: rather than half-closed: a token list that caught one spelling of an
#: attribute walk and not another would read as coverage while providing none.
#:
#: ⚠ **THE APP LABEL LEFT THIS LIST IN SLICE 3, WHICH IS THE SLICE IT WAS
#: WAITING FOR (#320).** The rule's own message said it: *"slice 2 owns the
#: declaration; slice 3 owns every behaviour the declaration selects"*, and the
#: behaviour slice 3 owns is a cost that reads what the tenant declared —
#: whether the supplier reports it, and whether this Event Type carries one at
#: all. A gate written for the window in which nothing rated against the
#: catalogue cannot also be the gate for the window after.
#:
#: What is left is narrower and still bites, and it is the half that was always
#: load-bearing: **a behavioural module may not name a catalogue CLASS.** The
#: four class names below are the ORM entry points, so the rule now says a
#: rating path reaches the declaration through the one read that answers in
#: plain data (``apps.platform.event_types.costing.cost_declaration``) and never
#: by querying the records itself. Both controls for that are at the foot of
#: this module — the sanctioned import passes, a direct ``EventType`` query does
#: not — because "the app label is allowed now" with nothing showing what still
#: fails would be a rule that had quietly stopped existing.
CATALOGUE_TOKENS = ("Provider", "EventCategory", "EventType",
                    "MeasurementConcept")

#: Taking a key apart. ``startswith``/``endswith`` are here because a shortcut
#: that only *tests* the prefix has still decided which supplier it is looking
#: at from the spelling of a key.
_SPLIT_METHODS = frozenset({
    "split", "rsplit", "partition", "rpartition",
    "removeprefix", "removesuffix", "startswith", "endswith",
})
#: The regular-expression entry points, matched on the METHOD NAME alone. A
#: precompiled ``_PATTERN.match(...)`` names no module, so requiring an ``re.``
#: receiver would have missed the tidier half of the shortcut.
_REGEX_FUNCTIONS = frozenset({"match", "search", "fullmatch", "split", "findall"})

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}


# ---------------------------------------------------------------------------
# The model registry: what may hold a satellite, and what a satellite may hold
# ---------------------------------------------------------------------------

def model_label(model):
    return f"{model._meta.app_label}.{model.__name__}"


def site_of(model, field=None):
    module = model.__module__.replace(".", "/")
    suffix = f"::{model.__name__}"
    if field is not None:
        suffix += f".{field.name}"
    return f"ubb-platform/{module}.py{suffix}"


def _local_fields(model):
    """Concrete fields plus many-to-many — everything the model declares itself.

    Reverse accessors are excluded because they are the far side of a relation
    some other model declared, and that model is walked in its own right.
    """
    return list(model._meta.concrete_fields) + list(model._meta.many_to_many)


def _satellite_of(field):
    if field.is_relation and field.related_model in (Provider, EventCategory):
        return field.related_model
    return None


def classify_holder(model, field):
    """``optional-satellite`` and ``no-record-beneath``, on one relation."""
    satellite = _satellite_of(field)
    if satellite is None:
        return None
    name = satellite.__name__

    if model_label(model) not in SATELLITE_HOLDERS:
        return (
            RULE_BENEATH, site_of(model, field),
            f"{site_of(model, field)} holds a {name}. Only "
            f"{sorted(SATELLITE_HOLDERS)} may — the account-level record "
            f"beneath the supplier was removed from the model by a later "
            f"decision and must not be rebuilt ({TICKET}). Adding a second "
            f"holder is a modelling decision, so it belongs in a decision "
            f"record and in this list, in that order",
        )
    if field.many_to_many:
        return (
            RULE_BENEATH, site_of(model, field),
            f"{site_of(model, field)} holds MANY {name} records. An Event Type "
            f"has one optional supplier and one primary category ({TICKET}) — "
            f"a many-to-many says something the model does not mean, and it "
            f"cannot express which one is primary. Declare a nullable "
            f"ForeignKey",
        )
    if not (field.null and field.blank):
        return (
            RULE_OPTIONAL, site_of(model, field),
            f"{site_of(model, field)} REQUIRES a {name}. Both satellites "
            f"are optional: a tenant metering its own internal work has no "
            f"supplier and must not be made to invent a fictitious one to "
            f"satisfy a schema, and an Event Type with no category is a normal "
            f"Event Type rather than an incomplete one ({TICKET}). Declare it "
            f"`null=True, blank=True`",
        )
    return None


def classify_holder_arity(model, fields):
    """``no-record-beneath`` — one supplier and one primary category, at most.

    On the model rather than on a field, because "one primary per Event Type"
    is a statement about how many relations there are and no single relation
    can see the others. A ``secondary_category`` beside the primary one passes
    every field-level rule in this file and still contradicts the ticket.
    """
    hits = []
    for satellite in (Provider, EventCategory):
        held = [f for f in fields if _satellite_of(f) is satellite]
        if len(held) < 2:
            continue
        hits.append((
            RULE_BENEATH, site_of(model),
            f"{site_of(model)} holds {len(held)} {satellite.__name__} "
            f"relations ({', '.join(f.name for f in held)}). One optional "
            f"supplier and ONE PRIMARY category ({TICKET}) — a second relation "
            f"is a second answer to a question with one answer, and nothing "
            f"downstream would know which of them meant it",
        ))
    return hits


def classify_category_shape(field):
    """``category-stays-small`` — no hierarchy, no effective-dating."""
    if field.name in HIERARCHY_FIELD_NAMES or field.related_model is EventCategory:
        return (
            RULE_SMALL, site_of(EventCategory, field),
            f"{site_of(EventCategory, field)} gives the category a HIERARCHY. "
            f"It is one level, and a second one is a decision rather than a "
            f"refinement ({TICKET})",
        )
    if field.name in DATING_FIELD_NAMES:
        return (
            RULE_SMALL, site_of(EventCategory, field),
            f"{site_of(EventCategory, field)} effective-dates the category. "
            f"The dating and the historical reproducibility the originating "
            f"decision required were retired when the category left the "
            f"pricing ladder and became analytics-only — dating a value that "
            f"reaches no money reproduces nothing ({TICKET})",
        )
    return None


def field_words(name):
    """A field name's words, for the rules that read a name for meaning.

    One definition, shared with the gate next door (#262) rather than copied
    there — a second money rule splitting names its own way is two rules that
    agree until the day they do not, and the one that drifted would be the one
    nobody was looking at.
    """
    return set(re.split(r"[^a-z]+", name.lower()))


def classify_monetary_field(model, field):
    """``never-monetary`` — a satellite carries no cost and no price."""
    named_money = sorted(field_words(field.name) & MONETARY_FIELD_WORDS)
    typed_money = field.get_internal_type() in MONETARY_FIELD_TYPES
    if not named_money and not typed_money:
        return None
    why = f"is named for money ({', '.join(named_money)})" if named_money \
        else f"is a {field.get_internal_type()}"
    return (
        RULE_MONETARY, site_of(model, field),
        f"{site_of(model, field)} {why}. Neither satellite is a monetary "
        f"input: the category cannot reach a cost or a price by any path, and "
        f"the supplier's cost lives on the rate that resolves through it, "
        f"never on the supplier record ({TICKET})",
    )


def classify_stringly_typed_supplier(model, field):
    """``identity-not-spelling`` — the catalogue names no supplier as a value.

    A real ForeignKey named ``provider`` is not caught by this, and must not
    be: its ``name`` is ``provider`` and its ``is_relation`` is True, so it
    leaves by the first line. What is caught is the column that carries an
    identity or a spelling while declaring no relation — the shape that holds a
    Provider without being walkable as one.
    """
    if field.is_relation or field.name not in STRINGLY_TYPED_SUPPLIER_NAMES:
        return None
    return (
        RULE_IDENTITY, site_of(model, field),
        f"{site_of(model, field)} names a supplier without holding one. "
        f"Supplier cost resolution keys on the Provider record's IDENTITY, and "
        f"a column that carries a key or a bare identifier is neither walkable "
        f"nor constrained — a rename or a delete on the far side leaves it "
        f"pointing at nothing, silently ({TICKET}). Declare a ForeignKey",
    )


def _walk_registry():
    hits = []
    seen = set()
    for model in first_party_models():
        seen.add(model_label(model))
        in_catalogue = model._meta.app_config.name == CATALOGUE_APP
        fields = _local_fields(model)
        hits.extend(classify_holder_arity(model, fields))
        for field in fields:
            hits.extend(filter(None, [
                classify_holder(model, field),
                classify_monetary_field(model, field)
                if model in (Provider, EventCategory) else None,
                classify_category_shape(field) if model is EventCategory else None,
                classify_stringly_typed_supplier(model, field)
                if in_catalogue else None,
            ]))
    return hits, seen


_REGISTRY_HITS, _MODELS_SEEN = _walk_registry()


def _registry_failures(rule):
    return "\n".join(message for r, _, message in _REGISTRY_HITS if r == rule)


def test_the_registry_walk_actually_saw_the_models():
    """Vacuity guard: an absence proved over an empty registry proves nothing.

    The floor is a floor rather than the exact count, because the exact count
    moves with every model any slice adds, and a guard that has to be edited by
    unrelated work is a guard that gets raised until it stops failing. What
    carries the weight is the named list beneath it: those six must be visible,
    and a walk that lost the app registry loses all of them at once.
    """
    assert len(_MODELS_SEEN) > 50, f"only walked {len(_MODELS_SEEN)} models"
    for expected in ("event_types.EventType", "event_types.Provider",
                     "event_types.EventCategory",
                     "grouping_fields.GroupingField", "work.TaskType",
                     "tenants.Tenant", "usage.Posting"):
        assert expected in _MODELS_SEEN, f"the walk did not visit {expected}"


def test_no_model_requires_a_satellite():
    failures = _registry_failures(RULE_OPTIONAL)
    assert not failures, "\n" + failures


def test_no_record_sits_beneath_the_supplier():
    failures = _registry_failures(RULE_BENEATH)
    assert not failures, "\n" + failures


def test_the_category_has_no_hierarchy_and_no_effective_dating():
    failures = _registry_failures(RULE_SMALL)
    assert not failures, "\n" + failures


def test_neither_satellite_carries_money():
    failures = _registry_failures(RULE_MONETARY)
    assert not failures, "\n" + failures


def test_the_catalogue_names_no_supplier_as_a_string():
    failures = _registry_failures(RULE_IDENTITY)
    assert not failures, "\n" + failures


# ---------------------------------------------------------------------------
# The source: nothing behavioural reads either satellite, and nobody parses a
# supplier out of an Event Type key
# ---------------------------------------------------------------------------

def _iter_production_sources(roots):
    """Every production ``.py`` under ``roots`` — no tests, no migrations."""
    for root in roots:
        base = PLATFORM_ROOT / root
        paths = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for path in paths:
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            yield path, rel.as_posix()


def classify_catalogue_reach(label, tree):
    """``never-monetary`` — a behavioural module that can see the catalogue.

    Over the parsed tree rather than the raw text, and matching whole name
    segments rather than substrings, because both halves of that are load
    bearing. A raw-text scan would fail a billing module for mentioning the
    catalogue in a comment, which is the shape of gate that gets deleted rather
    than obeyed; and a substring match would fail ``queries.py`` for the word
    "Provider" inside an English sentence.

    Wider than an import check for one reason: ``apps.get_model("event_types",
    "Provider")`` imports nothing, and it is exactly how a boundary gets
    crossed by someone who has read a boundary test.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)):
            found |= set(_dotted_name(node).split(".")) & set(CATALOGUE_TOKENS)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # The label or class name as data — whole, so prose never matches.
            found |= {node.value} & set(CATALOGUE_TOKENS)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = [getattr(node, "module", "") or ""]
            imported += [alias.name for alias in node.names]
            for name in imported:
                found |= set(name.split(".")) & set(CATALOGUE_TOKENS)
    if not found:
        return None
    return (
        RULE_MONETARY, label,
        f"{label} names the catalogue class {', '.join(sorted(found))}. No "
        f"rating path, cost resolution or spend ceiling may query the "
        f"catalogue itself: neither satellite ever reaches money, the grouping "
        f"is analytics-only, and what a declaration says about cost is read "
        f"through apps.platform.event_types.costing.cost_declaration, which "
        f"answers in plain data ({TICKET}, #320)",
    )


def _dotted_name(node):
    """The dotted name an expression resolves to, or ``""`` if it does not.

    Whole-name rather than last-segment, because the subject hides in either
    half: ``self.event_type.partition(...)`` names it on the right and
    ``event_type.key`` on the left, and a check that read only one end would
    miss whichever the shortcut happened to use.
    """
    parts = []
    while True:
        if isinstance(node, ast.Name):
            parts.append(node.id)
            break
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
            continue
        if isinstance(node, (ast.Subscript, ast.Starred)):
            node = node.value
            continue
        if isinstance(node, ast.Call):
            node = node.func
            continue
        break
    return ".".join(reversed(parts))


#: A name segment that IS a tenant's Event Type key: ``event_type`` itself or a
#: qualified form of it. Two exclusions, and both are the point rather than
#: tidiness. ``webhook_event_type`` is a UBB-owned notification name, dotted by
#: design (``usage.recorded``), and splitting one is correct code. The plural
#: ``event_types`` is this app's own label, so ``event_types.__name__.split(
#: ".")`` is a module path being read and not a key being taken apart. A
#: substring test would have failed both, and a gate that fails correct code is
#: a gate that gets deleted rather than obeyed.
_EVENT_TYPE_KEY_SEGMENT = re.compile(r"^event_type(_[a-z0-9_]+)?$")


def _is_event_type_expression(node):
    """Whether an expression names a tenant's Event Type key."""
    return any(_EVENT_TYPE_KEY_SEGMENT.match(segment)
               for segment in _dotted_name(node).split("."))


def classify_key_parsing(label, tree):
    """``identity-not-spelling`` — the shortcut that must never be taken.

    Returns ``(hits, subjects)``: the violations, and how many Event-Type-key
    expressions were looked at. The second number is the vacuity guard's input —
    a walk that never met the subject proves nothing about it.
    """
    hits, subjects = [], 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)) and _is_event_type_expression(node):
            subjects += 1

        parsed = None
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) \
                and _is_event_type_expression(node.value):
            # `event_type.key[:6]` — the same decision, spelled shorter.
            parsed = "a slice"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _SPLIT_METHODS \
                    and _is_event_type_expression(func.value):
                parsed = f"{func.attr}()"
            elif isinstance(func, ast.Attribute) and func.attr in _REGEX_FUNCTIONS \
                    and any(_is_event_type_expression(arg) for arg in node.args):
                # Receiver-agnostic: `re.match(p, k)` and `_PATTERN.match(k)`
                # decide the same thing, and only one of them names `re`.
                parsed = f"{func.attr}()"

        if parsed is not None:
            hits.append((
                RULE_IDENTITY, f"{label}:{node.lineno}",
                f"{label}:{node.lineno} takes an Event Type key apart with "
                f"{parsed}. Supplier cost resolution keys on the Provider "
                f"record's IDENTITY and never on parsing a supplier's name out "
                f"of a key ({TICKET}) — a tenant renaming their own key would "
                f"silently re-attribute their cost, and a key that happens to "
                f"contain a separator would decide what a call cost. Follow the "
                f"foreign key",
            ))
    return hits, subjects


def _walk_sources():
    reach, parsing, scanned, subjects = [], [], [], 0
    behavioural = {label for _, label in _iter_production_sources(BEHAVIOURAL_SURFACES)}
    for path, label in _iter_production_sources(("apps", "core", "api")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scanned.append(label)
        if label in behavioural:
            hit = classify_catalogue_reach(label, tree)
            if hit is not None:
                reach.append(hit)
        found, seen = classify_key_parsing(label, tree)
        parsing.extend(found)
        subjects += seen
    return reach, parsing, scanned, subjects, behavioural


_REACH, _PARSING, _SCANNED, _KEY_SUBJECTS, _BEHAVIOURAL = _walk_sources()


def test_the_source_walk_actually_read_the_behavioural_surfaces():
    """Vacuity guard, in both halves.

    The reach half must have read the modules that decide money; the parsing
    half must have met Event Type keys at all, or its silence is an artefact of
    a walk that found nothing to look at.
    """
    assert len(_SCANNED) > 200, f"only scanned {len(_SCANNED)} modules"
    for expected in ("apps/metering/pricing/models.py",
                     "apps/metering/usage/models.py",
                     "apps/metering/queries.py",
                     "apps/metering/handlers.py",
                     "apps/billing/gating/services/risk_service.py",
                     "core/money.py"):
        assert expected in _BEHAVIOURAL, f"the walk did not read {expected}"
        assert expected in _SCANNED, f"the walk did not read {expected}"
    assert _KEY_SUBJECTS > 40, (
        f"only {_KEY_SUBJECTS} Event-Type-key expressions were classified — the "
        f"parsing check may be reading a tree it cannot see the subject in")


def test_nothing_behavioural_reads_either_satellite():
    assert not _REACH, "\n" + "\n".join(message for _, _, message in _REACH)


def test_no_code_path_parses_a_supplier_out_of_an_event_type_key():
    assert not _PARSING, "\n" + "\n".join(message for _, _, message in _PARSING)


# ---------------------------------------------------------------------------
# Negative controls — every rule above, shown to fail.
#
# The models are REAL Django models under ``isolate_apps``, pushed through the
# same classifiers the registry walk uses; the source controls are parsed with
# the same walker. A control that hand-built the classifier's input would prove
# the classifier works on input shaped like its own expectations, which is not
# the question ``test_model_naming.py`` asks either.
# ---------------------------------------------------------------------------

CATALOGUE_LABEL = "event_types"


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_required_satellite_is_flagged():
    class EventType(models.Model):
        provider = models.ForeignKey(Provider, on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_holder(EventType, EventType._meta.get_field("provider"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_OPTIONAL
    assert "REQUIRES a Provider" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_nullable_but_mandatory_satellite_is_flagged():
    """``null=True`` alone still makes the form and the serializer demand one."""
    class EventType(models.Model):
        category = models.ForeignKey(EventCategory, on_delete=models.PROTECT,
                                     null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_holder(EventType, EventType._meta.get_field("category"))
    assert hit is not None
    assert hit[0] == RULE_OPTIONAL


@isolate_apps(CATALOGUE_APP)
def test_negative_control_an_account_beneath_the_supplier_is_flagged():
    class ProviderAccount(models.Model):
        provider = models.ForeignKey(Provider, on_delete=models.CASCADE,
                                     null=True, blank=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_holder(ProviderAccount,
                          ProviderAccount._meta.get_field("provider"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_BENEATH
    assert "account-level record" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_any_second_holder_is_flagged_whatever_it_is_called():
    """The rule is the allowlist, not the word "account" in a class name."""
    class BillingProfile(models.Model):
        supplier = models.ForeignKey(Provider, on_delete=models.CASCADE,
                                     null=True, blank=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_holder(BillingProfile,
                          BillingProfile._meta.get_field("supplier"))
    assert hit is not None and hit[0] == RULE_BENEATH


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_event_type_may_hold_both_optionally():
    class EventType(models.Model):
        provider = models.ForeignKey(Provider, on_delete=models.PROTECT,
                                     null=True, blank=True)
        category = models.ForeignKey(EventCategory, on_delete=models.PROTECT,
                                     null=True, blank=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert classify_holder(EventType, EventType._meta.get_field("provider")) is None
    assert classify_holder(EventType, EventType._meta.get_field("category")) is None


@isolate_apps(CATALOGUE_APP)
def test_positive_control_an_event_type_carrying_neither_is_valid():
    """The internal-work case, at the layer that would otherwise forbid it.

    A tenant metering its own work declares no supplier and groups under no
    category, and the declaration is complete rather than half-finished. The
    Event Type itself arrives in the ticket after this one; what is settled here
    is that neither satellite may be made a precondition of it.
    """
    class EventType(models.Model):
        key = models.SlugField(max_length=128)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert [f for f in _local_fields(EventType)
            if f.is_relation and f.related_model in (Provider, EventCategory)] == []
    assert [classify_holder(EventType, field) for field in _local_fields(EventType)] \
        == [None] * len(_local_fields(EventType))


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_second_category_relation_is_flagged():
    """"One primary per Event Type" — the rule no single field can see."""
    class EventType(models.Model):
        category = models.ForeignKey(EventCategory, on_delete=models.PROTECT,
                                     null=True, blank=True,
                                     related_name="primary_for")
        secondary_category = models.ForeignKey(EventCategory,
                                               on_delete=models.PROTECT,
                                               null=True, blank=True,
                                               related_name="secondary_for")

        class Meta:
            app_label = CATALOGUE_LABEL

    # Every field passes on its own, which is exactly why the arity rule exists.
    assert [classify_holder(EventType, field)
            for field in _local_fields(EventType)] == [None] * 3

    hits = classify_holder_arity(EventType, _local_fields(EventType))
    assert len(hits) == 1
    rule, _, message = hits[0]
    assert rule == RULE_BENEATH
    assert "ONE PRIMARY category" in message
    assert "category, secondary_category" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_many_to_many_satellite_is_flagged():
    class EventType(models.Model):
        providers = models.ManyToManyField(Provider, blank=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_holder(EventType, EventType._meta.get_field("providers"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_BENEATH
    assert "MANY Provider records" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_category_parent_is_flagged():
    class Nested(models.Model):
        parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_category_shape(Nested._meta.get_field("parent"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_SMALL
    assert "HIERARCHY" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_self_relation_under_another_name_is_flagged():
    class Rolled(models.Model):
        rolls_up_to = models.ForeignKey(EventCategory, on_delete=models.CASCADE,
                                        null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_category_shape(Rolled._meta.get_field("rolls_up_to"))
    assert hit is not None and hit[0] == RULE_SMALL


@isolate_apps(CATALOGUE_APP)
def test_negative_control_an_effective_dated_category_is_flagged():
    class Dated(models.Model):
        effective_from = models.DateTimeField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_category_shape(Dated._meta.get_field("effective_from"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_SMALL
    assert "analytics-only" in message


@isolate_apps(CATALOGUE_APP)
def test_positive_control_row_stamps_are_not_effective_dating():
    class Stamped(models.Model):
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)
        retired_at = models.DateTimeField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    for name in ("created_at", "updated_at", "retired_at"):
        assert classify_category_shape(Stamped._meta.get_field(name)) is None


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_monetary_satellite_field_is_flagged():
    class Priced(models.Model):
        default_cost_micros = models.BigIntegerField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_monetary_field(Priced, Priced._meta.get_field("default_cost_micros"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_MONETARY
    assert "monetary input" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_decimal_on_a_satellite_is_flagged_by_its_type():
    """A money field that avoids every money word is still a money field."""
    class Weighted(models.Model):
        weighting = models.DecimalField(max_digits=10, decimal_places=4)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_monetary_field(Weighted, Weighted._meta.get_field("weighting"))
    assert hit is not None and hit[0] == RULE_MONETARY


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_stringly_typed_supplier_is_flagged():
    class Loose(models.Model):
        provider = models.CharField(max_length=100)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_stringly_typed_supplier(Loose, Loose._meta.get_field("provider"))
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_IDENTITY
    assert "ForeignKey" in message


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_bare_identifier_column_is_flagged():
    """Holding an identity while declaring no relation — the tidiest evasion.

    It passes ``no-record-beneath`` (there is no relation to walk) and looks
    like it honours "keys on identity". It does neither: nothing constrains it,
    nothing cascades, and a delete on the far side leaves it dangling.
    """
    class Detached(models.Model):
        provider_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    field = Detached._meta.get_field("provider_id")
    assert classify_holder(Detached, field) is None, "no relation to walk"
    hit = classify_stringly_typed_supplier(Detached, field)
    assert hit is not None
    assert hit[0] == RULE_IDENTITY
    assert "bare identifier" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_positive_control_a_real_foreign_key_named_provider_is_not_flagged():
    """The rule must not fire on the shape it is asking for."""
    class EventType(models.Model):
        provider = models.ForeignKey(Provider, on_delete=models.PROTECT,
                                     null=True, blank=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    field = EventType._meta.get_field("provider")
    assert classify_stringly_typed_supplier(EventType, field) is None
    assert classify_holder(EventType, field) is None


def _reach(label, source):
    return classify_catalogue_reach(label, ast.parse(source))


def test_negative_control_a_behavioural_module_naming_the_catalogue_is_flagged():
    hit = _reach(
        "apps/metering/pricing/services/rating.py",
        "from apps.platform.event_types.models import Provider\n",
    )
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_MONETARY
    assert "Provider" in message


def test_negative_control_a_rating_path_querying_the_declaration_is_flagged():
    """The door slice 3 opened, and the one it did not (#320).

    A rating path may now ask what an Event Type declares about cost. It asks
    the read that answers in plain data; querying the record itself hands a
    rating path a live row it can save, and puts a second definition of "what
    this declaration means for cost" wherever the second caller writes one.
    """
    hit = _reach(
        "apps/metering/pricing/services/pricing_service.py",
        "def cost_for(tenant, key):\n"
        "    return EventType.objects.get(tenant=tenant, key=key)\n",
    )
    assert hit is not None
    assert hit[0] == RULE_MONETARY and "EventType" in hit[2]


def test_positive_control_the_costing_read_is_not_a_crossing():
    """The sanctioned door, asserted as passing rather than assumed to.

    This is verbatim what `pricing_service.py` does, and if it ever stops
    passing the production module is what goes red — so the rule and the one
    reach it permits are pinned in the same place.
    """
    assert _reach(
        "apps/metering/pricing/services/pricing_service.py",
        "from apps.platform.event_types.costing import cost_declaration\n"
        "declaration = cost_declaration(tenant=tenant, key=key)\n",
    ) is None


def test_negative_control_a_rating_path_reading_the_grouping_is_flagged():
    """The analytics opt-in, read where money is decided (#264).

    Nothing here holds a relation, so the model-registry rule next door has
    nothing to walk — and grouping rates by a heading a tenant edits for a
    chart is exactly what "analytics-only" refuses.
    """
    hit = _reach(
        "apps/metering/pricing/services/rating.py",
        "def rate_for(measurement):\n"
        "    return MeasurementConcept.objects.get(pk=measurement.concept_id)\n",
    )
    assert hit is not None
    assert hit[0] == RULE_MONETARY and "MeasurementConcept" in hit[2]


def test_negative_control_a_catalogue_fetched_by_label_is_flagged():
    """The crossing that is not an import, and would survive an import check."""
    hit = _reach(
        "apps/billing/gating/services/risk_service.py",
        'Category = apps.get_model("event_types", "EventCategory")\n',
    )
    assert hit is not None and hit[0] == RULE_MONETARY


def test_positive_control_prose_about_a_provider_is_not_a_crossing():
    """The gate must not fail a module for the English word in a sentence.

    ``apps/metering/queries.py`` really does say "Provider + billed cost
    totals" in a docstring, and a raw-text scan would have failed it on day one
    — which is how a gate gets deleted instead of obeyed.
    """
    assert _reach(
        "apps/metering/queries.py",
        '"""Provider + billed cost totals for one customer."""\n'
        "# event_types is where the catalogue will live\n"
        "total = provider_cost_micros + markup_micros\n",
    ) is None


def _classify_snippet(source, label="apps/metering/pricing/synthetic.py"):
    hits, subjects = classify_key_parsing(label, ast.parse(source))
    return hits, subjects


def test_negative_control_splitting_an_event_type_key_is_flagged():
    hits, subjects = _classify_snippet('provider = event_type_key.split("/")[0]\n')
    assert len(hits) == 1
    rule, _, message = hits[0]
    assert rule == RULE_IDENTITY
    assert "split()" in message and ":1 " in message
    assert subjects >= 1


def test_negative_control_partitioning_an_attribute_is_flagged():
    hits, _ = _classify_snippet(
        "def resolve(self):\n"
        '    supplier, _, rest = self.event_type.partition(":")\n'
    )
    assert len(hits) == 1
    assert hits[0][0] == RULE_IDENTITY
    assert ":2 " in hits[0][2]


def test_negative_control_a_regex_over_an_event_type_key_is_flagged():
    hits, _ = _classify_snippet(
        "import re\n"
        'name = re.match(r"^([a-z]+)", event_type.key)\n'
    )
    assert len(hits) == 1
    assert "match()" in hits[0][2]


def test_negative_control_a_precompiled_pattern_is_flagged_too():
    """It names no module, so a check anchored on ``re.`` would have missed it."""
    hits, _ = _classify_snippet("name = _SUPPLIER_PATTERN.match(event_type_key)\n")
    assert len(hits) == 1 and hits[0][0] == RULE_IDENTITY


def test_negative_control_slicing_an_event_type_key_is_flagged():
    hits, _ = _classify_snippet('vendor = event_type.key[:6]\n')
    assert len(hits) == 1
    assert "a slice" in hits[0][2]


def test_negative_control_trimming_a_prefix_is_flagged():
    hits, _ = _classify_snippet('rest = event_type_key.removeprefix("acme/")\n')
    assert len(hits) == 1 and "removeprefix()" in hits[0][2]


def test_negative_control_merely_testing_a_prefix_is_flagged():
    """A test rather than a parse, and the same decision either way."""
    hits, _ = _classify_snippet('if event_type.key.startswith("acme/"):\n    pass\n')
    assert len(hits) == 1 and "startswith()" in hits[0][2]


def test_positive_control_a_webhook_event_type_may_be_split():
    """UBB's own notification names are dotted BY DESIGN.

    ``webhook_event_type`` is a live registered concept whose values look like
    ``usage.recorded``; splitting one is correct code, and a substring match on
    "event_type" would have turned this gate red on the first module to do it.
    """
    hits, _ = _classify_snippet('domain, _, name = webhook_event_type.partition(".")\n')
    assert hits == []


def test_positive_control_this_apps_own_label_is_not_a_key():
    """``event_types`` plural is the app, not a tenant's Event Type key."""
    assert _classify_snippet('app, _, mod = event_types.__name__.rpartition(".")\n')[0] == []
    assert _classify_snippet('names = config.event_types.split(",")\n')[0] == []


def test_positive_control_following_the_foreign_key_is_not_flagged():
    hits, subjects = _classify_snippet(
        "provider_id = event_type.provider_id\n"
        "provider = Provider.objects.get(pk=provider_id)\n"
    )
    assert hits == []
    assert subjects >= 1, "the control did not exercise the subject it claims to"


def test_positive_control_splitting_something_that_is_not_an_event_type_key():
    hits, _ = _classify_snippet('head, _, tail = webhook_name.partition(".")\n')
    assert hits == []
