"""What the declaration must never grow (#262, extended by #263 and #264).

Four of the six rules below are **absences**, and three of those are an absence
a merged decision once required: the grouping axes were on the cost key, the
cost amount was on the declaration, and two operational variants of one call
were one averaged thing. Each was removed by a later decision, and an
implementer reading only the originating document would rebuild all three. An
absence asserted in a docstring is a comment; these are properties of the model
registry, so they are classified here.

============================  ================================================
``no-grouping-axis``          The declaration carries no grouping axis. They
                              were deleted outright from the cost key, which now
                              collapses to tenant + Event Type + measurement +
                              timestamp — and a Measurement Concept groups
                              measurement RECORDS, which is why it is not a role
                              on the Grouping Field vocabulary either.
``no-cost-amount``            The declaration carries no cost amount. The
                              exact-variant-then-explicit-default ladder is
                              gone, so there is nothing here for an amount to
                              hang off; a cost lives on the rate that resolves
                              through this record. On the Measurement it is the
                              other half of the same ruling: a quantity has a
                              unit, a reported supplier cost has a currency, and
                              the second is a SIBLING of the quantities rather
                              than one of them.
``one-response-shape``        One active response shape per Event Type, and one
                              model that declares one. The named extension for a
                              second is a sparse mapping profile BENEATH the
                              Event Type.
``variants-stay-independent`` Nothing relates one Event Type to another. Two
                              operational variants with genuinely different
                              supplier costs are two costable things, and a
                              relation between them is the beginning of
                              averaging them.
``a-quantity-stands-alone``   The grouping a quantity may be opted into is
                              optional and singular. A required one makes an
                              analytics heading a precondition for declaring a
                              quantity; a many-to-many makes "which grouping is
                              this in" a question with several answers.
``grouping-is-analytics-``    Nothing but a declaration may point at that
``only``                      grouping. A rate or a posting that could reach it
                              would have made an analytics opt-in into a
                              costing input, which is the one thing #264 says
                              it can never become.
============================  ================================================

**The three subjects.** The first two rules are asked of the Event Type, of the
Measurement declared beneath it and of the grouping that Measurement may point
at, and of nothing else: asking them of the whole tree would fail every model
that legitimately carries a price or an axis, which is most of the money-bearing
ones. The rest are asked of everything, because every one of them is about what
a SECOND model might quietly declare.

**Where the fourth absence lives.** "No account-level record beneath the
supplier" is ``no-record-beneath`` in
``test_event_type_satellite_invariants.py`` next door, whose allowlist named
``event_types.EventType`` a ticket before the model existed. It is not restated
here: two encodings of one rule drift, and the one that drifts is the one nobody
is looking at.

**The obligations** (``tests/contracts/README.md``): every rule has a negative
control that pushes a synthetic violation through the real classifier, and the
walk has a vacuity guard, because a check over an absence that silently read
nothing is worse than no check at all.

**What this cannot see.** A cost amount reachable *through* the Event Type —
``event_type.provider.something`` inside a rating service — names nothing this
walker can classify. What catches that is the import matrix plus the behavioural
reach check next door; what this catches is the column being added here.
"""
import re

from django.db import models
from django.test.utils import isolate_apps

from apps.platform.event_types.models import (
    EventCategory,
    EventType,
    Measurement,
    MeasurementConcept,
    Provider,
)
from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue
# One definition of "every model a UBB app declares", and one definition of what
# makes a field a money field — both shared with the gates next door rather than
# copied, for the reason those files give: two encodings of one fact drift.
from apps.platform.tests.test_event_type_satellite_invariants import (
    MONETARY_FIELD_TYPES,
    MONETARY_FIELD_WORDS,
    _local_fields,
    field_words,
    model_label,
    site_of,
)
from apps.platform.tests.test_model_naming import first_party_models

TICKET = "#262"
CATALOGUE_APP = "apps.platform.event_types"

#: The records the two absences below are asked of. The Measurement joined in
#: #263 and the grouping in #264, and each is the next place a cost amount or a
#: grouping axis would land if either came back — every one of them looking
#: reasonable at the moment it was written. A quantity is the natural home for
#: "what this one costs" right up until you notice there are two answers and no
#: rule for which wins; a grouping is the natural home for "what everything
#: under this heading costs", which is the same mistake one level up and reaches
#: further, because a heading spans suppliers.
#:
#: The grouping is tenant-level rather than part of any one declaration, so this
#: tuple is "what these two rules are stated about" and not "what a declaration
#: is made of" — ``DECLARATION_PARTS`` below is the second of those and is
#: deliberately not the same list.
DECLARATION_MODELS = (EventType, Measurement, MeasurementConcept)

#: Who may point at the opt-in grouping. Exactly the declared quantity: the
#: grouping exists to say two quantities mean the same thing, and any other
#: holder is something else having found a use for it. A rate or a posting
#: reaching it is the whole of what "analytics-only" forbids.
CONCEPT_HOLDERS = frozenset({"event_types.Measurement"})

#: The grouping held as a value rather than as a relation — the evasion that
#: gets past every rule above at once, because it carries the identity while
#: declaring nothing to walk. #261's review found exactly this shape for the
#: supplier (a bare ``provider_id = UUIDField()``) and closed it by name; the
#: same hole is open on anything a later slice adds, so it is closed here in
#: the same way rather than found again.
#:
#: Asked of every model INCLUDING the one holder, because the objection is
#: different there: the declared quantity may hold this grouping, and holding it
#: as a loose identifier is still unconstrained, uncascaded and dangling the
#: moment the far side goes.
GROUPING_IDENTIFIER_NAMES = frozenset({
    "concept_id", "concept_key", "concept_uuid", "concept_ref",
    "measurement_concept", "measurement_concept_id", "measurement_concept_key",
})

#: The records that are PART of one Event Type's declaration, and the single
#: field on each by which they hang off it. A part necessarily names an Event
#: Type — that is what makes it a part — and naming its own parent is not the
#: thing ``variants-stay-independent`` is about, which is one costable thing
#: being related to another. Spelled as the exact field set so that a SECOND
#: Event Type arriving on a part is still caught, and so that adding a part is
#: a line somebody writes rather than a rule that quietly stopped applying.
DECLARATION_PARTS = {
    "event_types.Measurement": frozenset({"event_type"}),
}

RULE_GROUPING = "no-grouping-axis"
RULE_AMOUNT = "no-cost-amount"
RULE_SHAPE = "one-response-shape"
RULE_VARIANTS = "variants-stay-independent"
RULE_OPTIONAL = "a-quantity-stands-alone"
RULE_ANALYTICS = "grouping-is-analytics-only"

#: The named extension for a second response shape, recorded here because the
#: rule below is only half a ruling without it. Refusing the second shape
#: without naming where one goes reads as "this was not thought about", and the
#: thing it must not be is a duplicated Event Type — which would fork a
#: money-bearing declaration to solve a rendering problem.
NAMED_EXTENSION = ("a sparse mapping profile beneath the Event Type, never a "
                   "duplicated Event Type")

#: A grouping axis, by name. The relation forms are caught by their target
#: model instead, so a rename on the far side cannot slip past this list.
GROUPING_FIELD_NAMES = frozenset(
    {f"dim{slot}" for slot in range(1, 11)}
    | {"grouping_field", "grouping_field_key", "grouping_field_value",
       "grouping_key", "grouping_value", "axis", "axes", "grouping_axis",
       "grouping_axes", "slot", "slots"}
)
GROUPING_MODELS = (GroupingField, GroupingFieldValue)

#: Who may declare a response shape, and exactly which fields say so. Keyed by
#: model LABEL rather than by class identity, for the reason the negative
#: controls make concrete: a control that has to shadow the real class to build
#: a violation can never reach the branch that allows the real one, so the
#: allowance would be the one rule in this file nothing ever exercised.
SHAPE_DECLARERS = {
    "event_types.EventType": frozenset({"source_shape_id",
                                        "source_shape_label"}),
}
SHAPE_WORD = "shape"


def _class_words(name):
    """A CLASS name's words. ``ResponseShape`` is one lowercase run to the
    splitter above, which is why it needs its own reader rather than sharing
    one that would silently answer "no" for every model name."""
    return {word.lower() for word in re.findall(r"[A-Z][a-z]*|[a-z]+", name)}


def classify_grouping_axis(model, field):
    """``no-grouping-axis`` — the axes are gone from the cost key entirely."""
    if field.is_relation and field.related_model in GROUPING_MODELS:
        why = f"relates to {field.related_model.__name__}"
    elif field.name in GROUPING_FIELD_NAMES:
        why = "is named for a grouping axis"
    else:
        return None
    return (
        RULE_GROUPING, site_of(model, field),
        f"{site_of(model, field)} {why}. The declaration carries NO grouping "
        f"axis: they were deleted outright from the cost key, which collapses "
        f"to tenant + Event Type + measurement + timestamp ({TICKET}). A "
        f"grouping axis groups a POSTING for analytics; it never selects what "
        f"a call cost — and the grouping a Measurement may carry groups "
        f"measurement RECORDS, so it consumes no slot and is not a role on "
        f"this vocabulary either (#263)",
    )


def classify_cost_amount(model, field):
    """``no-cost-amount`` — a declaration is not a price list."""
    named_money = sorted(field_words(field.name) & MONETARY_FIELD_WORDS)
    typed_money = field.get_internal_type() in MONETARY_FIELD_TYPES
    if not named_money and not typed_money:
        return None
    why = f"is named for money ({', '.join(named_money)})" if named_money \
        else f"is a {field.get_internal_type()}"
    return (
        RULE_AMOUNT, site_of(model, field),
        f"{site_of(model, field)} {why}. The declaration carries no cost "
        f"amount ({TICKET}): the exact-variant-then-explicit-default ladder "
        f"was removed, so a cost lives on the rate that resolves THROUGH this "
        f"declaration and never on the declaration itself. A number here would "
        f"be a second answer to what a call cost, with no rule for which wins. "
        f"A Measurement is a quantity with a unit; a reported supplier cost is "
        f"money with a currency, and it is a SIBLING of the quantities rather "
        f"than one of them (#263)",
    )


def classify_variant_relation(model, field):
    """``variants-stay-independent`` — no Event Type names another one.

    The allowance is for the records that ARE one Event Type's declaration:
    a part holds exactly one Event Type and it is its parent, not a peer. Stated
    as the exact field set rather than as "a part may relate", so that a second
    Event Type appearing on a part is still the thing this rule is about — and
    keyed on the model LABEL for #262's reason, so a synthetic model can carry
    the real one's identity and the allowance branch is reachable by a control.
    """
    if not field.is_relation or field.related_model is not EventType:
        return None
    allowed = DECLARATION_PARTS.get(model_label(model))
    if allowed is not None and field.name in allowed and not field.many_to_many:
        return None
    return (
        RULE_VARIANTS, site_of(model, field),
        f"{site_of(model, field)} relates one Event Type to another. A batch "
        f"endpoint and a standard endpoint with genuinely different supplier "
        f"costs are TWO costable things ({TICKET}) — variants-are-not-"
        f"identities was reversed for exactly this case, and a link between "
        f"them is where averaging two different costs into one wrong number "
        f"starts. Declaring the variant separately is the supported shape",
    )


def classify_response_shape(model, fields):
    """``one-response-shape`` — one declaration of the shape, in one place.

    On the model rather than on a field, because "exactly one" is a statement
    about how many there are and no single field can see the others. Asked of
    every first-party model, not only the Event Type: a shape declared on a
    second record would be a second active shape however tidily it was housed.
    """
    declared = {field.name for field in fields
                if SHAPE_WORD in field_words(field.name)
                or (field.is_relation and field.related_model is not None
                    and SHAPE_WORD in _class_words(field.related_model.__name__))}
    if not declared:
        return None
    allowed = SHAPE_DECLARERS.get(model_label(model))
    if allowed is not None and declared == allowed:
        return None
    return (
        RULE_SHAPE, site_of(model),
        f"{site_of(model)} declares a response shape as {sorted(declared)}. "
        f"There is exactly ONE active response shape per Event Type in v1, "
        f"declared once at the Event Type as "
        f"{sorted(SHAPE_DECLARERS['event_types.EventType'])} so two quantities "
        f"beneath it can never disagree about which client they are mapped to "
        f"({TICKET}). The named extension is {NAMED_EXTENSION}",
    )


def classify_analytics_only(model, field):
    """``grouping-is-analytics-only`` — nothing but a declaration may reach it.

    The sharpest form of *"it can never become a costing input by accident"*.
    The accident does not look like a cost column on the grouping — that is
    caught above, and it is the version somebody would notice. It looks like a
    rate, a posting or a spend ceiling growing a foreign key to it, each of
    which reads as a reasonable local change and each of which makes an
    analytics heading select money. A grouping that a rate can see is a rate
    selector wearing an analytics name.

    Keyed on the model LABEL rather than on class identity for #262's reason:
    a synthetic control has to be able to carry the real record's identity, or
    the allowance branch is the one rule here nothing ever exercises.

    Two shapes, because the tidier one gets past a relation check entirely: a
    column that holds the grouping's identity while declaring no relation is
    the same reach with nothing to walk.
    """
    if field.is_relation:
        if field.related_model is not MeasurementConcept:
            return None
        if model_label(model) in CONCEPT_HOLDERS:
            return None
        return (
            RULE_ANALYTICS, site_of(model, field),
            f"{site_of(model, field)} reaches the opt-in grouping. Only "
            f"{sorted(CONCEPT_HOLDERS)} may (#264): the grouping is "
            f"ANALYTICS-ONLY, so it can never become a costing input and can "
            f"never block recording — and a rate, a posting or a ceiling that "
            f"can see it has made it one of those by the ordinary route, which "
            f"is a reasonable-looking foreign key rather than a decision "
            f"anybody took. Adding a holder is a modelling decision, so it "
            f"belongs in a decision record and in this list, in that order",
        )
    if field.name not in GROUPING_IDENTIFIER_NAMES:
        return None
    return (
        RULE_ANALYTICS, site_of(model, field),
        f"{site_of(model, field)} holds the opt-in grouping's identity without "
        f"holding the grouping. It passes every rule that walks a relation, "
        f"because there is no relation to walk (#264) — nothing constrains it, "
        f"nothing cascades, and a delete on the far side leaves it pointing at "
        f"a row that is gone. If a declared quantity is opting in, declare the "
        f"ForeignKey; if anything else is reading the grouping, that is the "
        f"reach this rule refuses",
    )


def classify_optional_grouping(model, field):
    """``a-quantity-stands-alone`` — the shape #264's grouping had to land in.

    The Measurement Concept is **tenant-level, opt-in and analytics-only**. This
    rule was written in #263, a ticket before the record existed — the way
    ``SATELLITE_HOLDERS`` named its model before there was one — so that the
    wrong shape would fail on arrival rather than be argued about afterwards.
    It now holds a real column in place.

    Two ways for it to land wrong, and both are one of #264's own fences taken
    down. A REQUIRED assignment makes an analytics grouping a precondition for
    declaring a quantity, when *"an event whose declaration carries no grouping
    records exactly as one whose declaration does"*. And a MANY assignment makes
    "which grouping is this quantity in" a question with several answers, when
    the opt-in is to one.

    Stated over everything a declaration part points at other than its own
    parent, rather than over a field name nobody has chosen yet: a rule keyed on
    a guessed spelling is a rule the real commit walks past. Keyed on the model
    LABEL rather than on class identity, so a synthetic control can carry the
    real record's identity and actually reach this branch — #262 shipped the
    other spelling and review caught it.
    """
    parent = DECLARATION_PARTS.get(model_label(model))
    if parent is None or not field.is_relation or field.name in parent:
        return None
    if field.many_to_many:
        why = "may be assigned to MANY of them"
    elif not (field.null and field.blank):
        why = "is required"
    else:
        return None
    return (
        RULE_OPTIONAL, site_of(model, field),
        f"{site_of(model, field)} {why}. A declared quantity stands alone: the "
        f"analytics grouping is tenant-level, OPT-IN and to ONE grouping "
        f"(#264), so a quantity records identically whether or not a tenant has "
        f"grouped it — and it can never block recording. If this is that "
        f"grouping arriving, make it optional and singular; if it is something "
        f"else, it is a relation on a declaration that nothing has decided",
    )


def _walk_registry():
    hits, seen, fields_seen = [], set(), 0
    for model in first_party_models():
        seen.add(model_label(model))
        fields = _local_fields(model)
        fields_seen += len(fields)
        hits.extend(filter(None, [classify_response_shape(model, fields)]))
        for field in fields:
            declares = model in DECLARATION_MODELS
            hits.extend(filter(None, [
                classify_variant_relation(model, field),
                classify_optional_grouping(model, field),
                classify_analytics_only(model, field),
                # The two absences are the declaration's own. Asking them of the
                # whole tree would fail every model that legitimately carries a
                # price or an axis, which is most of the money-bearing ones.
                classify_grouping_axis(model, field) if declares else None,
                classify_cost_amount(model, field) if declares else None,
            ]))
    return hits, seen, fields_seen


_HITS, _MODELS_SEEN, _FIELDS_SEEN = _walk_registry()


def _failures(rule):
    return "\n".join(message for name, _, message in _HITS if name == rule)


def test_the_walk_actually_saw_the_declaration():
    """Vacuity guard: four of the six rules below are absences.

    The Event Type by name, because it is the subject and a walk that lost it
    would report a clean sweep of absences over a tree it never read; the satellites
    and the Grouping Field registry because they are what the rules are stated
    AGAINST, and a walk that could not see them could not tell a relation to one
    from a relation to anything else.
    """
    assert len(_MODELS_SEEN) > 50, f"only walked {len(_MODELS_SEEN)} models"
    for expected in ("event_types.EventType", "event_types.Provider",
                     "event_types.EventCategory", "event_types.Measurement",
                     "event_types.MeasurementConcept",
                     "grouping_fields.GroupingField", "usage.UsageEvent"):
        assert expected in _MODELS_SEEN, f"the walk did not visit {expected}"
    assert _FIELDS_SEEN > 300, f"only classified {_FIELDS_SEEN} fields"
    assert len(_local_fields(EventType)) >= 11, (
        "the Event Type's own fields were not read")
    assert len(_local_fields(Measurement)) >= 9, (
        "the Measurement's own fields were not read")
    # The grouping's own relation, read from the far side. The rule that
    # matters most about this record is about who POINTS at it, and a walk that
    # could not see the one legitimate holder could not tell it from the
    # illegitimate ones either.
    assert [f.name for f in _local_fields(Measurement)
            if f.related_model is MeasurementConcept] == ["concept"]


def test_the_event_type_carries_no_grouping_axis():
    failures = _failures(RULE_GROUPING)
    assert not failures, "\n" + failures


def test_the_event_type_carries_no_cost_amount():
    failures = _failures(RULE_AMOUNT)
    assert not failures, "\n" + failures


def test_exactly_one_response_shape_is_declared_per_event_type():
    failures = _failures(RULE_SHAPE)
    assert not failures, "\n" + failures


def test_no_event_type_names_another_event_type():
    failures = _failures(RULE_VARIANTS)
    assert not failures, "\n" + failures


def test_a_declared_quantity_stands_alone():
    failures = _failures(RULE_OPTIONAL)
    assert not failures, "\n" + failures


def test_nothing_but_a_declaration_reaches_the_opt_in_grouping():
    failures = _failures(RULE_ANALYTICS)
    assert not failures, "\n" + failures


# ---------------------------------------------------------------------------
# Negative controls — every rule above, shown to fail, on REAL Django models
# pushed through the same classifiers the registry walk uses.
# ---------------------------------------------------------------------------

CATALOGUE_LABEL = "event_types"


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_grouping_relation_is_flagged():
    class EventType(models.Model):
        grouping_field = models.ForeignKey(GroupingField, on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_grouping_axis(EventType,
                                 EventType._meta.get_field("grouping_field"))
    assert hit is not None and hit[0] == RULE_GROUPING
    assert "GroupingField" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_bare_axis_column_is_flagged_by_its_name():
    """The evasion the relation check cannot see: an axis held as a value.

    A slot column declaring no relation is exactly how the axes sat on the
    usage row, and it is the shape someone reaching for the old model would
    reach for first.
    """
    class EventType(models.Model):
        dim1 = models.CharField(max_length=64)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_grouping_axis(EventType, EventType._meta.get_field("dim1"))
    assert hit is not None and hit[0] == RULE_GROUPING


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_cost_column_is_flagged():
    class EventType(models.Model):
        provider_cost_micros = models.BigIntegerField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_cost_amount(
        EventType, EventType._meta.get_field("provider_cost_micros"))
    assert hit is not None and hit[0] == RULE_AMOUNT


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_decimal_is_flagged_by_its_type_alone():
    """A money column that avoids every money word still gets caught.

    ``default_charge`` reads as configuration rather than as a price, which is
    exactly why the type is checked as well as the name.
    """
    class EventType(models.Model):
        default_per_call = models.DecimalField(max_digits=12, decimal_places=6)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_cost_amount(
        EventType, EventType._meta.get_field("default_per_call"))
    assert hit is not None and hit[0] == RULE_AMOUNT
    assert "DecimalField" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_costing_method_is_not_a_cost_amount():
    """The control that stops the money check from being unsatisfiable.

    ``costing_method`` says how a cost is DERIVED and carries no number. A
    check that failed it would have to be weakened until it stopped failing,
    which is how a gate becomes decorative.
    """
    class EventType(models.Model):
        costing_method = models.CharField(max_length=32)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert classify_cost_amount(
        EventType, EventType._meta.get_field("costing_method")) is None


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_cost_on_the_quantity_is_flagged():
    """The reported supplier cost, folded into the quantities (#263 §D2).

    The natural mistake, and it reads as tidy: a Measurement already says where
    a number comes from, so why not let one of them be the cost? Because a
    quantity has a unit and money has a currency — folding them makes the unit
    mean "currency", gives the value type a money shape, and puts a figure
    governed by a shared cost bound under a caller-set unbounded integer. It is
    a SIBLING of the quantities, and #266 declares it as one.
    """
    class Measurement(models.Model):
        provider_cost_micros = models.BigIntegerField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_cost_amount(
        Measurement, Measurement._meta.get_field("provider_cost_micros"))
    assert hit is not None and hit[0] == RULE_AMOUNT


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_currency_on_the_quantity_is_flagged():
    """The same fold, arriving from the other end.

    A currency beside a quantity is the column somebody adds when the cost is
    already there in spirit, and it is the one that makes the unit meaningless.
    """
    class Measurement(models.Model):
        currency = models.CharField(max_length=3)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_cost_amount(Measurement,
                               Measurement._meta.get_field("currency"))
    assert hit is not None and hit[0] == RULE_AMOUNT


@isolate_apps(CATALOGUE_APP)
def test_positive_control_a_unit_is_not_a_currency():
    """The control that stops the money rule from making a quantity unbuildable.

    ``unit`` is the noun beside the number. A check that failed it would have to
    be weakened until it stopped failing, which is how a gate becomes decorative
    — and it is a live risk here, because "minor unit" is money's own English.
    """
    class Measurement(models.Model):
        unit = models.CharField(max_length=64)
        required_for_costing = models.BooleanField(default=False)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert [classify_cost_amount(Measurement, field)
            for field in _local_fields(Measurement)] == [None] * 3


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_grouping_slot_on_the_quantity_is_flagged():
    """The Measurement Concept, built as a Grouping Field (#263, #264).

    It groups measurement RECORDS rather than events, so it is not a role on
    that vocabulary and consumes no slot. Reaching for the registry next door is
    the obvious thing to do with the word "grouping" in hand, and it would take
    an analytics-only opt-in and give it an axis that selects postings.
    """
    class Measurement(models.Model):
        grouping_field = models.ForeignKey(GroupingField,
                                           on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_grouping_axis(
        Measurement, Measurement._meta.get_field("grouping_field"))
    assert hit is not None and hit[0] == RULE_GROUPING


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_second_shape_column_is_flagged():
    """The Event Type itself, grown a second shape.

    The synthetic class carries the real one's label, so this reaches the
    allowance branch and fails it — rather than passing because the classifier
    did not recognise the model, which is what a control keyed on class
    identity would have done.
    """
    class EventType(models.Model):
        source_shape_id = models.CharField(max_length=100)
        source_shape_label = models.CharField(max_length=200)
        fallback_shape_id = models.CharField(max_length=100)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(EventType) in SHAPE_DECLARERS, (
        "the control has to be the model the allowance is about")
    hit = classify_response_shape(EventType, _local_fields(EventType))
    assert hit is not None and hit[0] == RULE_SHAPE
    assert "fallback_shape_id" in hit[2]
    # The refusal names where a second shape actually goes.
    assert NAMED_EXTENSION in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_declared_pair_is_allowed():
    """The allowance branch, exercised — the half the rule is useless without.

    A classifier that flagged every shape field whatever declared it would
    make the Event Type unbuildable, and the registry walk would say so; but
    it would say so identically to a walk that had simply gone wrong.
    """
    class EventType(models.Model):
        source_shape_id = models.CharField(max_length=100)
        source_shape_label = models.CharField(max_length=200)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert classify_response_shape(EventType, _local_fields(EventType)) is None


@isolate_apps(CATALOGUE_APP)
def test_negative_control_dropping_half_the_pair_is_flagged_too():
    """Checked in both directions, for the reason the counted gates give.

    An allowance stated as "at most these" would let the label be deleted and
    the shape go unnamed for every wrapper UBB does not recognise.
    """
    class EventType(models.Model):
        source_shape_id = models.CharField(max_length=100)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_response_shape(EventType, _local_fields(EventType))
    assert hit is not None and hit[0] == RULE_SHAPE


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_shape_housed_on_its_own_record_is_flagged():
    """Tidier, and still a second active shape.

    Moving the second shape onto a record of its own is what an implementer
    does after reading a rule about columns, so the rule is about the model —
    and the relation is deliberately named something that says nothing, so
    what catches it is the model it points AT rather than the field's own
    spelling.
    """
    class ResponseShape(models.Model):
        class Meta:
            app_label = CATALOGUE_LABEL

    class MappingProfile(models.Model):
        target = models.ForeignKey(ResponseShape, on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    fields = _local_fields(MappingProfile)
    assert not any(SHAPE_WORD in field_words(field.name) for field in fields), (
        "the control has to be caught by the relation, not by a field name")
    hit = classify_response_shape(MappingProfile, fields)
    assert hit is not None and hit[0] == RULE_SHAPE


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_set_of_event_types_gathered_together_is_flagged():
    """The shape the rule exists for, spelled as plainly as it ever would be.

    A record holding several Event Types is a record that has something to say
    about them jointly, and the only thing slice 2 has to say about two
    variants is that their costs are separate.
    """
    class CostGroup(models.Model):
        members = models.ManyToManyField(EventType)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_variant_relation(CostGroup,
                                    CostGroup._meta.get_field("members"))
    assert hit is not None and hit[0] == RULE_VARIANTS


@isolate_apps(CATALOGUE_APP)
def test_negative_control_the_friendly_spelling_is_flagged_too():
    """``parent_event_type`` is the spelling that sounds like housekeeping.

    It is the same claim as ``averages_with`` — that one variant's cost is not
    entirely its own — and it exercises the same branch a self-relation on the
    Event Type would, because the rule is about the model a field POINTS AT.
    (A true ``ForeignKey("self")`` cannot be synthesised here: under
    ``isolate_apps`` "self" resolves to the throwaway class, not to the record
    the rule is stated about.)
    """
    class Ancestry(models.Model):
        parent_event_type = models.ForeignKey(EventType, null=True,
                                              on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_variant_relation(
        Ancestry, Ancestry._meta.get_field("parent_event_type"))
    assert hit is not None and hit[0] == RULE_VARIANTS


@isolate_apps(CATALOGUE_APP)
def test_positive_control_a_declaration_part_may_name_its_own_parent():
    """The allowance branch, exercised.

    The synthetic model carries the real one's label, so this reaches the
    allowance and passes it — rather than passing because the classifier failed
    to recognise the model, which is what a control keyed on class identity
    would have done (#262 shipped exactly that mistake and it was caught in
    review).
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(Measurement) in DECLARATION_PARTS, (
        "the control has to be the model the allowance is about")
    assert classify_variant_relation(
        Measurement, Measurement._meta.get_field("event_type")) is None


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_second_event_type_on_a_part_is_flagged():
    """Checked in both directions.

    An allowance stated as "a part may relate to an Event Type" would let a
    quantity declared beneath one call quietly answer for another — which is
    averaging two costable things, arrived at from underneath.
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
        also_priced_as = models.ForeignKey(EventType, null=True,
                                           on_delete=models.PROTECT,
                                           related_name="+")

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_variant_relation(
        Measurement, Measurement._meta.get_field("also_priced_as"))
    assert hit is not None and hit[0] == RULE_VARIANTS


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_part_may_not_gather_event_types():
    """The allowance is for ONE parent, so a many-to-many is still a hit."""
    class Measurement(models.Model):
        event_type = models.ManyToManyField(EventType)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_variant_relation(
        Measurement, Measurement._meta.get_field("event_type"))
    assert hit is not None and hit[0] == RULE_VARIANTS


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_required_grouping_is_flagged():
    """#264's grouping, landed as a precondition for declaring a quantity.

    The synthetic model carries the real one's label, so this reaches the rule
    rather than being ignored as an unknown class — which is the difference
    between a tripwire and a comment.
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
        concept = models.ForeignKey(EventCategory, on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(Measurement) in DECLARATION_PARTS, (
        "the control has to be the model the rule is about")
    hit = classify_optional_grouping(Measurement,
                                     Measurement._meta.get_field("concept"))
    assert hit is not None and hit[0] == RULE_OPTIONAL
    assert "required" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_grouping_to_many_is_flagged():
    """The evasion the optionality check alone cannot see.

    A many-to-many is optional in the sense that it may be empty, and it takes
    #264's other fence down instead: the opt-in is to ONE grouping, and "which
    grouping is this quantity in" is a question with one answer.
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
        concepts = models.ManyToManyField(EventCategory)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_optional_grouping(Measurement,
                                     Measurement._meta.get_field("concepts"))
    assert hit is not None and hit[0] == RULE_OPTIONAL


@isolate_apps(CATALOGUE_APP)
def test_positive_control_an_optional_grouping_is_allowed():
    """The shape #264 is supposed to land, shown to pass.

    A rule that flagged every grouping would make #264 unbuildable, and the
    registry walk would say so — identically to a walk that had simply gone
    wrong. The parent link is exercised here too: it is required by
    construction, and a rule that could not tell it from a grouping would fire
    on every declaration part there will ever be.
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
        concept = models.ForeignKey(EventCategory, null=True, blank=True,
                                    on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert [classify_optional_grouping(Measurement, field)
            for field in _local_fields(Measurement)] == [None] * 3


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_rate_reaching_the_grouping_is_flagged():
    """The costing input, arriving as the most reasonable change in the world.

    "Price all the quantities under this heading the same way" is a sentence a
    product owner will say, and the foreign key that implements it turns an
    analytics opt-in into a rate selector — after which a tenant re-filing two
    quantities under one heading changes what their customers are charged.
    """
    class Rate(models.Model):
        concept = models.ForeignKey(MeasurementConcept, null=True, blank=True,
                                    on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_analytics_only(Rate, Rate._meta.get_field("concept"))
    assert hit is not None and hit[0] == RULE_ANALYTICS
    assert "ANALYTICS-ONLY" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_negative_control_the_recorded_event_reaching_the_grouping_is_flagged():
    """The other direction, and the one that could block a recording.

    A posting that resolves a grouping on the way in has put an analytics
    heading on the path an event travels, where a missing or unknown one is one
    refactor away from a refusal. Nullable and optional does not save it: the
    rule is that nothing on that path may reach this record at all.
    """
    class Posting(models.Model):
        measurement_concept = models.ForeignKey(
            MeasurementConcept, null=True, blank=True, on_delete=models.SET_NULL)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_analytics_only(
        Posting, Posting._meta.get_field("measurement_concept"))
    assert hit is not None and hit[0] == RULE_ANALYTICS


@isolate_apps(CATALOGUE_APP)
def test_negative_control_gathering_groupings_is_flagged_too():
    """Whatever the arity, the objection is that this model can see it."""
    class SpendCeiling(models.Model):
        applies_to = models.ManyToManyField(MeasurementConcept)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_analytics_only(SpendCeiling,
                                  SpendCeiling._meta.get_field("applies_to"))
    assert hit is not None and hit[0] == RULE_ANALYTICS


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_declared_quantity_may_hold_one():
    """The allowance branch, exercised — the half the rule is useless without.

    A rule that flagged every holder would make #264 unbuildable, and the
    registry walk would say so identically to a walk that had simply gone
    wrong. The synthetic model carries the real one's label, so this reaches
    the allowance rather than passing for want of recognising the class.
    """
    class Measurement(models.Model):
        event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
        concept = models.ForeignKey(MeasurementConcept, null=True, blank=True,
                                    on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(Measurement) in CONCEPT_HOLDERS, (
        "the control has to be the model the allowance is about")
    assert [classify_analytics_only(Measurement, field)
            for field in _local_fields(Measurement)] == [None] * 3
    # And the shape it landed in still satisfies the rule written for it a
    # ticket earlier: optional, and to exactly one.
    assert [classify_optional_grouping(Measurement, field)
            for field in _local_fields(Measurement)] == [None] * 3


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_bare_grouping_identifier_is_flagged():
    """The reach with nothing to walk, and the tidiest of the lot.

    It passes the relation branch (there is no relation), it looks like it
    honours "keys on identity", and it does neither: nothing constrains it and
    a delete on the far side leaves it dangling. #261's review found this exact
    shape for the supplier; the fence is closed here rather than found twice.
    """
    class Rate(models.Model):
        measurement_concept_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    field = Rate._meta.get_field("measurement_concept_id")
    hit = classify_analytics_only(Rate, field)
    assert hit is not None and hit[0] == RULE_ANALYTICS
    assert "no relation to walk" in hit[2]


@isolate_apps(CATALOGUE_APP)
def test_negative_control_the_holder_may_not_hold_it_loosely_either():
    """The one model allowed to opt in is not allowed to opt in by UUID.

    The allowance is for the relation, and the objection to a loose identifier
    is a different one — so the model label cannot excuse this shape.
    """
    class Measurement(models.Model):
        concept_id = models.UUIDField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert model_label(Measurement) in CONCEPT_HOLDERS, (
        "the control has to be the model the allowance is about")
    hit = classify_analytics_only(Measurement,
                                  Measurement._meta.get_field("concept_id"))
    assert hit is not None and hit[0] == RULE_ANALYTICS


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_real_foreign_key_is_not_a_bare_identifier():
    """The rule must not fire on the shape it is asking for.

    Django gives a ForeignKey an ``attname`` of ``concept_id``, and a check
    that read the attname rather than the field name would fail the very column
    #264 shipped — which is how a gate gets weakened until it stops meaning
    anything.
    """
    class Measurement(models.Model):
        concept = models.ForeignKey(MeasurementConcept, null=True, blank=True,
                                    on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    field = Measurement._meta.get_field("concept")
    assert field.attname in GROUPING_IDENTIFIER_NAMES, (
        "the control is only meaningful while the attname is a listed name")
    assert classify_analytics_only(Measurement, field) is None


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_cost_on_the_grouping_is_flagged():
    """The same mistake one level up, and it reaches further than on a quantity.

    "Everything under this heading costs the same" is the sentence, and a
    heading spans suppliers — so a number here would price a Gemini call from a
    row an analyst edited to tidy up a chart.
    """
    class MeasurementConcept(models.Model):
        default_cost_micros = models.BigIntegerField(null=True)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_cost_amount(
        MeasurementConcept,
        MeasurementConcept._meta.get_field("default_cost_micros"))
    assert hit is not None and hit[0] == RULE_AMOUNT


@isolate_apps(CATALOGUE_APP)
def test_negative_control_a_slot_on_the_grouping_is_flagged():
    """The grouping, rebuilt as an analytics axis (#264).

    It groups measurement RECORDS rather than events, so it consumes no slot
    and appears nowhere in the slot map. Reaching for the registry next door is
    the obvious thing to do with the word "grouping" in hand, and it would
    spend one of the finite slots a real analytics axis needs.
    """
    class MeasurementConcept(models.Model):
        slot = models.CharField(max_length=8)

        class Meta:
            app_label = CATALOGUE_LABEL

    hit = classify_grouping_axis(MeasurementConcept,
                                 MeasurementConcept._meta.get_field("slot"))
    assert hit is not None and hit[0] == RULE_GROUPING


@isolate_apps(CATALOGUE_APP)
def test_positive_control_the_satellites_are_not_a_variant_relation():
    """The other direction: the two relations the Event Type is SUPPOSED to hold.

    A variant rule that flagged the supplier and the category would make the
    Event Type unbuildable, so it is shown here not to.
    """
    class EventType(models.Model):
        provider = models.ForeignKey(Provider, null=True, blank=True,
                                     on_delete=models.PROTECT)
        category = models.ForeignKey(EventCategory, null=True, blank=True,
                                     on_delete=models.PROTECT)

        class Meta:
            app_label = CATALOGUE_LABEL

    assert [classify_variant_relation(EventType, field)
            for field in _local_fields(EventType)] == [None] * 3
