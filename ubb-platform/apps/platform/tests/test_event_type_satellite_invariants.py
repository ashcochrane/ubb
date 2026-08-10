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
                             cost-resolution or spend-ceiling module reads
                             either one. Slice 2 owns the declaration; slice 3
                             owns every behaviour the declaration selects.
``identity-not-spelling``    Supplier cost resolution keys on the Provider's
                             identity. No code path parses a supplier's name
                             out of an Event Type key, and the catalogue names
                             no supplier as a string.
===========================  =================================================

**Why the allowlist names a model that does not exist yet.** The Event Type
arrives in the ticket after this one. Writing its name into
``SATELLITE_HOLDERS`` now is what makes ``no-record-beneath`` a gate rather than
a note: the second model to hold a Provider fails on arrival, whatever it is
called, instead of being argued about after it is built.

**The obligations** (``tests/contracts/README.md``, from the boundary walker
next door): every rule has a negative control that pushes a synthetic violation
through the real entry point, and every walk has a vacuity guard, because a
check over an absence that silently read nothing is worse than no check at all.
"""
import ast
import re
from pathlib import Path

from django.apps import apps
from django.db import models
from django.test.utils import isolate_apps

from apps.platform.event_types.models import EventCategory, Provider

# apps/platform/tests/test_event_type_satellite_invariants.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

TICKET = "#261"
CATALOGUE_APP = "apps.platform.event_types"
FIRST_PARTY_PACKAGE = "apps."

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

#: A supplier named as a string rather than held as a relation. The usage row
#: still carries exactly this shape and is deliberately out of scope: it is the
#: world slice 2 replaces, and the posting split owns its removal. The rule is
#: about the catalogue, which is being built now and has no excuse.
STRINGLY_TYPED_SUPPLIER_NAMES = frozenset({
    "provider", "provider_key", "provider_name", "provider_slug",
    "supplier", "supplier_key", "supplier_name", "supplier_slug",
})

#: Where a cost, a price or a spend ceiling is decided. If a satellite is
#: reachable from any of these, "nothing behavioural is wired" is false.
BEHAVIOURAL_SURFACES = (
    "apps/metering/pricing",   # rating and rate selection
    "apps/metering/usage",     # the posting and what it cost
    "apps/billing",            # drawdown, invoicing and the spend ceilings
    "core/money.py",           # the money primitives themselves
)

#: What reaching the catalogue looks like from another module, whether it is
#: imported or fetched by label.
CATALOGUE_TOKENS = ("event_types", "EventCategory")

_SPLIT_METHODS = frozenset({"split", "rsplit", "partition", "rpartition"})
_REGEX_FUNCTIONS = frozenset({"match", "search", "fullmatch", "split", "findall"})

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}


# ---------------------------------------------------------------------------
# The model registry: what may hold a satellite, and what a satellite may hold
# ---------------------------------------------------------------------------

def first_party_models():
    """Every model a UBB app declares.

    ``django.contrib`` and third-party tables are somebody else's vocabulary,
    the same reason ``test_model_naming.py`` gives for the same exclusion.
    """
    return [
        model for model in apps.get_models()
        if model._meta.app_config is not None
        and model._meta.app_config.name.startswith(FIRST_PARTY_PACKAGE)
    ]


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


def classify_holder(model, field):
    """``optional-satellite`` and ``no-record-beneath``, on one relation."""
    if not field.is_relation or field.related_model not in (Provider, EventCategory):
        return None
    satellite = field.related_model.__name__

    if model_label(model) not in SATELLITE_HOLDERS:
        return (
            RULE_BENEATH, site_of(model, field),
            f"{site_of(model, field)} holds a {satellite}. Only "
            f"{sorted(SATELLITE_HOLDERS)} may — the account-level record "
            f"beneath the supplier was removed from the model by a later "
            f"decision and must not be rebuilt ({TICKET}). Adding a second "
            f"holder is a modelling decision, so it belongs in a decision "
            f"record and in this list, in that order",
        )
    if not (field.null and field.blank):
        return (
            RULE_OPTIONAL, site_of(model, field),
            f"{site_of(model, field)} REQUIRES a {satellite}. Both satellites "
            f"are optional: a tenant metering its own internal work has no "
            f"supplier and must not be made to invent a fictitious one to "
            f"satisfy a schema, and an Event Type with no category is a normal "
            f"Event Type rather than an incomplete one ({TICKET}). Declare it "
            f"`null=True, blank=True`",
        )
    return None


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


def classify_monetary_field(model, field):
    """``never-monetary`` — a satellite carries no cost and no price."""
    words = set(re.split(r"[^a-z]+", field.name.lower()))
    named_money = sorted(words & MONETARY_FIELD_WORDS)
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
    """``identity-not-spelling`` — the catalogue names no supplier as a string."""
    if field.is_relation or field.name not in STRINGLY_TYPED_SUPPLIER_NAMES:
        return None
    return (
        RULE_IDENTITY, site_of(model, field),
        f"{site_of(model, field)} names a supplier as a value rather than "
        f"holding one by identity. Supplier cost resolution keys on the "
        f"Provider record's identity, which is what survives a tenant "
        f"renaming their own handle ({TICKET}) — declare a ForeignKey",
    )


def _walk_registry():
    hits = []
    seen = set()
    for model in first_party_models():
        seen.add(model_label(model))
        in_catalogue = model._meta.app_config.name == CATALOGUE_APP
        for field in _local_fields(model):
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
    """Vacuity guard: an absence proved over an empty registry proves nothing."""
    assert len(_MODELS_SEEN) > 30, f"only walked {len(_MODELS_SEEN)} models"
    for expected in ("event_types.Provider", "event_types.EventCategory",
                     "grouping_fields.GroupingField", "work.TaskType",
                     "tenants.Tenant", "usage.UsageEvent"):
        assert expected in _MODELS_SEEN, f"the walk did not visit {expected}"


def test_no_model_requires_a_satellite():
    assert not _registry_failures(RULE_OPTIONAL), "\n" + _registry_failures(RULE_OPTIONAL)


def test_no_record_sits_beneath_the_supplier():
    assert not _registry_failures(RULE_BENEATH), "\n" + _registry_failures(RULE_BENEATH)


def test_the_category_has_no_hierarchy_and_no_effective_dating():
    assert not _registry_failures(RULE_SMALL), "\n" + _registry_failures(RULE_SMALL)


def test_neither_satellite_carries_money():
    assert not _registry_failures(RULE_MONETARY), "\n" + _registry_failures(RULE_MONETARY)


def test_the_catalogue_names_no_supplier_as_a_string():
    assert not _registry_failures(RULE_IDENTITY), "\n" + _registry_failures(RULE_IDENTITY)


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


def classify_catalogue_reach(label, source):
    """``never-monetary`` — a behavioural module that can see the catalogue.

    Token-level rather than import-level on purpose. ``apps.get_model(
    "event_types", "Provider")`` is not an import, and it is exactly how a
    boundary gets crossed by someone who has read a boundary test.
    """
    found = sorted({token for token in CATALOGUE_TOKENS if token in source})
    if not found:
        return None
    return (
        RULE_MONETARY, label,
        f"{label} names {', '.join(found)}. Nothing behavioural reads either "
        f"satellite in slice 2: no rating path, no cost resolution and no "
        f"spend ceiling. Slice 2 owns the declaration; slice 3 owns every "
        f"behaviour the declaration selects ({TICKET})",
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


def _is_event_type_expression(node):
    return "event_type" in _dotted_name(node)


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
        if not isinstance(node, ast.Call):
            continue

        parsed = None
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _SPLIT_METHODS \
                and _is_event_type_expression(func.value):
            parsed = f"{func.attr}()"
        elif isinstance(func, ast.Attribute) and func.attr in _REGEX_FUNCTIONS \
                and _dotted_name(func.value) == "re" \
                and any(_is_event_type_expression(arg) for arg in node.args):
            parsed = f"re.{func.attr}()"

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
        source = path.read_text(encoding="utf-8")
        scanned.append(label)
        if label in behavioural:
            hit = classify_catalogue_reach(label, source)
            if hit is not None:
                reach.append(hit)
        found, seen = classify_key_parsing(label, ast.parse(source, filename=str(path)))
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
                     "apps/billing/gating/services/risk_service.py",
                     "core/money.py"):
        assert expected in _BEHAVIOURAL, f"the walk did not read {expected}"
        assert expected in _SCANNED, f"the walk did not read {expected}"
    assert _KEY_SUBJECTS > 10, (
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


def test_negative_control_a_behavioural_module_naming_the_catalogue_is_flagged():
    hit = classify_catalogue_reach(
        "apps/metering/pricing/services/rating.py",
        "from apps.platform.event_types.models import Provider\n",
    )
    assert hit is not None
    rule, _, message = hit
    assert rule == RULE_MONETARY
    assert "event_types" in message


def test_negative_control_a_catalogue_fetched_by_label_is_flagged():
    """The crossing that is not an import, and would survive an import check."""
    hit = classify_catalogue_reach(
        "apps/billing/gating/services/risk_service.py",
        'Category = apps.get_model("event_types", "EventCategory")\n',
    )
    assert hit is not None and hit[0] == RULE_MONETARY


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
    assert "re.match()" in hits[0][2]


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
