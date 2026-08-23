"""The container is two entities now, and their COLUMNS are what say so (#368).

One table used to serve as both a book of supplier costs and a book of customer
prices, told apart by a `cost`/`price` word. The thing that word could never
express is the thing that is actually true of the two:

* **a cost is OBSERVED** — from a named supplier, in whatever currency that
  supplier bills — so a cost book is pinned to a provider and to a currency;
* **a price is DECIDED**, by the tenant, and does not move because the tenant
  switched supplier — so a Pricing Book is pinned to neither.

This module is where that is checked rather than described. The shape claims
are made **by asking the model layer for the columns**, not by constructing a
row and hoping the right thing happens: a row that merely fails to carry a
provider is one a future `AddField` would silently start carrying, while a
model that has no such field cannot.

⚠ **THE TWO HALVES ARE ENFORCED BY DIFFERENT MECHANISMS AND THIS MODULE SAYS
WHICH.** The cost book's currency is held at the DATABASE, by
`ck_cost_book_names_its_currency` — a cost book that does not say which
currency its supplier bills in prices nothing it can be trusted about. Its
provider is NOT held by a check, and that is deliberate rather than missing:
`""` is the tenant's provider-agnostic cost book, a real selection tier that
`PricingService._selected_cost_books` reads alongside the supplier's own, so a
constraint refusing it would delete a feature under cover of a rename. What is
enforced for the provider is that the COLUMN EXISTS on one entity and not on
the other, which is the claim being made.

It replaces `test_rate_card_container_model.py`, whose two cases were about the
single container and the record that assigned one to a customer — one entity
that no longer exists and one record this commit deletes.
"""
import pytest
from django.db import IntegrityError, transaction

from apps.metering.pricing.models import (
    NAMES_ITS_CURRENCY_CHECK, SITS_IN_AT_MOST_ONE_BOOK_CHECK,
    CostBook, PricingBook, Rate)
from apps.metering.pricing.tests._helpers import retired_kind_column
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


def _columns(model):
    return {field.name for field in model._meta.concrete_fields}


# --------------------------------------------------------------------------
# The shapes
# --------------------------------------------------------------------------

def test_a_cost_book_has_a_provider_and_a_currency():
    columns = _columns(CostBook)

    assert "provider_key" in columns
    assert "currency" in columns


def test_a_pricing_book_accepts_neither():
    """The other half, and the one that could not be said before.

    Asked of the MODEL rather than of a row: a Pricing Book that merely left a
    provider empty would be a Pricing Book that has one, and the sentence this
    slice exists to make true is that it has none.
    """
    columns = _columns(PricingBook)

    assert "provider_key" not in columns
    assert "currency" not in columns
    # And the word that used to stand in for both is on neither entity.
    # DERIVED FROM THE MIGRATION THAT DELETED IT, never spelled (#374): this
    # module is a living surface, and naming the token here would put its
    # ledger count over an entry that reaches zero in that same commit.
    assert retired_kind_column() not in columns
    assert retired_kind_column() not in _columns(CostBook)


def test_a_cost_book_that_names_no_currency_is_refused_at_the_database():
    """The DECLARED half, held by a check rather than by a default.

    The column has no default at all, so this is not "the empty string is
    unusual" — it is that a cost book cannot be born without saying which
    currency its supplier bills in. That is what keeps this column off the
    unowned-currency-column list: it is a declaration, not a stamped copy of
    the tenant's own frozen choice.
    """
    t = _tenant()

    with pytest.raises(IntegrityError) as caught:
        CostBook.objects.create(tenant=t, key="k", provider_key="openai")

    assert NAMES_ITS_CURRENCY_CHECK in str(caught.value)


def test_the_provider_agnostic_cost_book_is_still_writable():
    """The non-subject, named so its absence is not read as an oversight.

    `""` is a stated provider and means *whatever the supplier* — the tier
    resolution reads alongside the supplier's own book. A check refusing it
    would have deleted that, which is why the provider half of "a cost book is
    pinned to a provider and a currency" is a claim about the COLUMN and not
    about its value.
    """
    t = _tenant()

    book = CostBook.objects.create(tenant=t, key="any", provider_key="",
                                   currency="usd", is_default=True)

    assert book.provider_key == ""


# --------------------------------------------------------------------------
# What may exist at once
# --------------------------------------------------------------------------

def test_one_default_pricing_book_per_tenant():
    """The key lost two columns rather than gaining a meaning.

    It used to be (tenant, kind, provider, currency). The kind is a different
    table now, the provider is not something a price depends on, and the
    currency is the tenant's — so what is left is the sentence the constraint
    was always trying to say.
    """
    t = _tenant()
    PricingBook.objects.create(tenant=t, key="a", name="A", is_default=True)

    with pytest.raises(IntegrityError, match="uq_pricing_book_one_default"):
        PricingBook.objects.create(tenant=t, key="b", name="B", is_default=True)


def test_one_default_cost_book_per_supplier_and_currency():
    """The per-provider default survives on the cost side and only there.

    Both inserts share the provider so this isolates the `is_default` partial
    key from the unrelated (tenant, key) uniqueness beside it.
    """
    t = _tenant()
    CostBook.objects.create(tenant=t, key="gemini", provider_key="gemini",
                            currency="usd", is_default=True)

    with pytest.raises(IntegrityError,
                       match="uq_cost_book_one_default_per_provider"):
        CostBook.objects.create(tenant=t, key="gemini-2", provider_key="gemini",
                                currency="usd", is_default=True)


def test_two_suppliers_may_each_have_a_default_cost_book():
    """The positive control for the key above, without which it would pass on a
    constraint that refused a second default outright."""
    t = _tenant()
    CostBook.objects.create(tenant=t, key="gemini", provider_key="gemini",
                            currency="usd", is_default=True)

    second = CostBook.objects.create(tenant=t, key="openai",
                                     provider_key="openai", currency="usd",
                                     is_default=True)

    assert second.pk is not None


def test_one_override_book_per_customer():
    """What the deleted assignment record's uniqueness key became.

    That record was unique per (tenant, customer, currency) and pointed at a
    shared book. A customer's own rules live in a book that carries the
    customer, and a customer has at most one — the currency left the key with
    the column, and admits exactly what it admitted before, because a tenant
    has exactly one currency.
    """
    t = _tenant()
    c = Customer.objects.create(tenant=t, external_id="c1")
    PricingBook.objects.create(tenant=t, key="ov-1", customer=c)

    with pytest.raises(IntegrityError,
                       match="uq_pricing_book_one_override_per_customer"):
        PricingBook.objects.create(tenant=t, key="ov-2", customer=c)


# --------------------------------------------------------------------------
# A rule belongs to one of them
# --------------------------------------------------------------------------

def test_a_rule_cannot_sit_in_a_book_of_costs_and_a_book_of_prices_at_once():
    """The shape the discriminator used to admit, refused at the database.

    A rule carried a kind word copied from its book and free to disagree with
    it; there is no word now, only two pointers, and this is what stops one
    rule being reachable from both halves of the ladder at once.
    """
    t = _tenant()
    prices = PricingBook.objects.create(tenant=t, key="p", is_default=True)
    costs = CostBook.objects.create(tenant=t, key="c", provider_key="",
                                    currency="usd", is_default=True)

    with pytest.raises(IntegrityError) as caught:
        Rate.objects.create(
            tenant=t, measurement=declares_a_quantity(t, "tokens"),
            currency="usd", rate_per_unit_micros=1,
            pricing_book=prices, cost_book=costs)

    assert SITS_IN_AT_MOST_ONE_BOOK_CHECK in str(caught.value)


def test_a_rule_in_no_book_at_all_is_still_writable():
    """AT MOST one, not EXACTLY one, and the difference is stated rather than
    left to be inferred from the constraint's name.

    A rule with no book has been writable since before the container existed —
    the column has always been nullable and callers across this tree still rely
    on it — so refusing one would be a second, unrelated change riding on the
    split, with its own conversion. What the split makes impossible is the case
    above.
    """
    t = _tenant()

    rule = Rate.objects.create(
        tenant=t, measurement=declares_a_quantity(t, "tokens"),
        currency="usd", rate_per_unit_micros=1)

    assert rule.book is None


def test_a_rule_answers_with_the_book_it_is_in_whichever_kind_that_is():
    t = _tenant()
    prices = PricingBook.objects.create(tenant=t, key="p", is_default=True)
    costs = CostBook.objects.create(tenant=t, key="c", provider_key="",
                                    currency="usd", is_default=True)

    priced = Rate.objects.create(
        tenant=t, measurement=declares_a_quantity(t, "tokens"),
        currency="usd", rate_per_unit_micros=1, pricing_book=prices)
    cost = Rate.objects.create(
        tenant=t, measurement=declares_a_quantity(t, "other_tokens"),
        currency="usd", rate_per_unit_micros=1, cost_book=costs)

    assert priced.book == prices
    assert cost.book == costs


def test_a_book_says_which_column_points_at_it():
    """The dispatch, asserted where it is declared.

    Every reader that has a book and wants its rules asks the book which
    column is its own, rather than testing what type it is. Two entities, two
    answers, and they are the field names `Rate` actually carries.
    """
    assert PricingBook.REFERENCE_COLUMN == "pricing_book"
    assert CostBook.REFERENCE_COLUMN == "cost_book"
    for column in (PricingBook.REFERENCE_COLUMN, CostBook.REFERENCE_COLUMN):
        assert column in _columns(Rate)


# --------------------------------------------------------------------------
# The three acts that ceased with the entity
# --------------------------------------------------------------------------

#: The three acts, by their ordinary verbs. None of these is a retired word.
THE_VERBS_THAT_CEASED = ("created", "assigned", "published")

#: The migration that split the container, which is where the retired noun is
#: still legitimately written down.
THE_SPLIT = "0028_the_container_becomes_a_pricing_book_and_a_cost_book"


def the_retired_container():
    """The noun the deleted actions were named for, DERIVED from the rename.

    ⚠ **NOT SPELLED, AND THAT IS THE FIRST OF THE THREE TECHNIQUES RATHER THAN
    A FLOURISH.** The counts this slice pays are ceilings on SPREAD, not only
    on what is left to fix: a new module writing the word puts its ledger count
    over an entry, and the sweep refuses the rise outright — it is not a
    "record it and move on" finding. Deriving it costs one import and no
    authorisation, and it is what `test_the_rates_quantity_name_takes_the_
    canonical_name.py` already does for the column it renames.

    The name comes off the migration's OWN from-state, so no future rename
    needs an edit here: the table the container sat on before the split was the
    retired noun with a namespace prefix and a suffix that was only ever there
    to make room for the misnamed original.
    """
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    from apps.metering.pricing.tests._helpers import the_state_before

    migration = MigrationLoader(connection).get_migration("pricing", THE_SPLIT)
    was = the_state_before(migration).models[
        ("pricing", "ratecard")].options["db_table"]
    return was.removeprefix("ubb_").removesuffix("_container") + "."


def the_acts_that_ceased():
    prefix = the_retired_container()
    return tuple(prefix + verb for verb in THE_VERBS_THAT_CEASED)


@pytest.mark.django_db
def test_the_derivation_reaches_three_names_that_look_like_actions():
    """The vacuity guard for everything below it.

    A derivation that came back empty, or with a prefix that stopped being the
    retired noun, would make every case below true by iterating nothing — the
    exact shape a derived fixture has to be defended against.
    """
    names = the_acts_that_ceased()

    assert len(names) == 3
    for name in names:
        noun, _, verb = name.partition(".")
        assert noun and verb, name
        assert verb in THE_VERBS_THAT_CEASED, name


def test_the_registry_knows_none_of_the_three():
    from apps.platform.audit.actions import AUDIT_ACTIONS, is_registered_action

    for name in the_acts_that_ceased():
        assert name not in AUDIT_ACTIONS, name
        assert not is_registered_action(name), name


def test_the_recording_function_refuses_each_of_them():
    """`record()` refuses an unregistered name, and that is what made the
    deletion safe rather than merely defensible.

    It is the mechanism rather than the care: an action deleted while a route
    still wrote it fails loudly, so route and registry are forced into one
    commit and there is no window in which a dead action is written.
    """
    from apps.platform.audit.ledger import record

    tenant = _tenant()
    for name in the_acts_that_ceased():
        with pytest.raises(ValueError, match="unregistered audit"):
            record(action=name, tenant_id=tenant.id,
                   resource_type="pricing_book")


def test_no_surviving_action_names_the_retired_container():
    """The stronger form, over the whole registry.

    Asserting three names are absent says nothing about a fourth somebody adds
    later under the same retired noun — which is the shape a by-name check
    always has.
    """
    from apps.platform.audit.actions import AUDIT_ACTIONS

    surviving = [name for name in AUDIT_ACTIONS
                 if name.startswith(the_retired_container())]

    assert surviving == []


# --------------------------------------------------------------------------
# UBB ships no catalogue
# --------------------------------------------------------------------------

def test_a_new_tenant_starts_with_no_books_no_rules_and_no_markup():
    """**THE CONSTRAINT MOST LIKELY TO BE VIOLATED BY A HELPFUL DEFAULT.**

    UBB ships no catalogue: no starter Pricing Book, no starter cost book, no
    default rule set and no seeded markup rung. A tenant that has declared
    nothing HAS nothing, and resolution answers `unknown` rather than zero —
    which is the silently wrong price this programme exists to delete, and
    which a seeded row would put straight back.

    ⚠ **ASSERTED OVER A TENANT MADE THE ORDINARY WAY, AND OVER THE WHOLE
    REGISTRY RATHER THAN OVER THE MODELS THIS COMMIT ADDED.** A check naming
    only `PricingBook` and `CostBook` would stay green the day some other
    pricing model grew a helpful `post_save` default. What is being asserted is
    that creating a tenant writes nothing into this app at all.
    """
    from django.apps import apps as django_apps

    tenant = _tenant()

    seeded = {}
    for model in django_apps.get_app_config("pricing").get_models():
        if not any(f.is_relation and f.related_model is Tenant
                   for f in model._meta.concrete_fields):
            continue
        count = model.objects.filter(tenant=tenant).count()
        if count:
            seeded[model.__name__] = count

    assert seeded == {}, seeded


def test_the_migration_that_split_the_container_creates_no_row():
    """The other half, and the one a fixture cannot see.

    A data migration seeding a starter book would leave every EXISTING tenant
    with one, which no per-tenant assertion above would catch. This asserts the
    migration writes nothing at all: it carries no `RunPython`, forwards or in
    reverse.
    """
    from django.db import migrations
    from django.db.migrations.loader import MigrationLoader
    from django.db import connection

    migration = MigrationLoader(connection).get_migration(
        "pricing", "0028_the_container_becomes_a_pricing_book_and_a_cost_book")

    assert not [op for op in migration.operations
                if isinstance(op, (migrations.RunPython, migrations.RunSQL))]


# --------------------------------------------------------------------------
# The record that assigned a book to a customer
# --------------------------------------------------------------------------

def test_no_record_assigns_a_book_to_a_customer_any_more():
    """The third table is DELETED, not renamed (#193 §L, spec §1).

    Its job passed to the Plan's required book reference (#362), which is where
    a customer's pricing already resolves from. Asserted over the whole app's
    model registry rather than by importing a name — an `ImportError` around
    one symbol proves nothing about a differently-named model doing the same
    job, which is the shape #366 paid for one schema over.
    """
    from django.apps import apps as django_apps

    tables = {model._meta.db_table
              for model in django_apps.get_app_config("pricing").get_models()}

    assert not [t for t in tables if "assignment" in t], sorted(tables)


def test_no_resolution_rung_reads_an_assignment():
    """The service half of the same claim.

    The ladder had four ways a book could be selected for a customer and now
    has three. This asserts the rung is GONE rather than merely unused — a
    method left in place answering `None` would keep passing every behavioural
    test while the deletion had not happened.
    """
    from apps.metering.pricing.services.pricing_service import PricingService

    assert not [name for name in dir(PricingService) if "assign" in name.lower()]
