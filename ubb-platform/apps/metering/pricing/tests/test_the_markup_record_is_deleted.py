"""The tenant-level markup record is gone, and so are the acts it recorded (#369).

**WHAT THIS MODULE HOLDS.** One record carried a percentage — millionths of a
percent, under a money suffix — and a per-event flat amount, on a row per tenant
and a row per customer. It is deleted with its five routes, its two component
schemas and both of its audit action names, and the plan catalog's two markup
columns go with it. The claims here are that each of those really is absent, and
that the mechanism which made deleting the action names safe still holds.

**⚠ THE TWO RETIRED ACTION NAMES ARE DERIVED, NOT SPELLED, AND THAT IS FORCED
RATHER THAN STYLISTIC.** Their ledger entries reach ZERO in this commit — every
one of the five, across the backend, the console and the SDK. The sweep's counts
are ceilings on SPREAD as well as floors, so a new module writing either word
would put its count back over an entry that no longer exists and fail outright.
Deriving them costs one import and no authorisation, which is the first and
cheapest of the three techniques ticket 19 lists; the alternative — admitting
this file to the sweep's *checks-whose-subject-is-a-retired-word* rule — would
grow a PERMANENT exclusion, which #155 §3.2 forbids. #368 did exactly this for
the three book acts that ceased, and the derivation here takes the noun off the
DELETING migration's own from-state, so no future rename needs an edit.

**THE ROUTER HALF IS IN `api/v1/tests/test_the_markup_routes_that_ceased.py`**,
which asserts that none of the five paths is on the live API and that no
surviving route writes either name. It belongs there because its subject is the
router: an `apps/**/tests/` module reaching into `api.v1` is invisible to the
boundary walker, which excludes `tests/` (#367). It spells nothing retired
either — it walks the live API and asks what is NOT there.
"""
import pytest
from django.apps import apps as django_apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from apps.metering.pricing.tests._helpers import the_state_before
from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant

#: The migration that deletes the record — where the retired noun is still
#: legitimately written down, because the migrations tree is a declared sweep
#: exclusion and a deletion migration has to name what it deletes.
THE_DELETION = "0029_the_markup_record_is_deleted"

#: The two acts, as ordinary English verbs. Neither is a retired token on its
#: own; what was retired is each one joined to the noun below.
THE_VERBS_THAT_CEASED = ("set", "deleted")


def _tenant():
    return Tenant.objects.create(name="Markup", products=["metering"])


def the_retired_record():
    """The noun the deleted actions were named for, DERIVED from the deletion.

    The name comes off the migration's OWN from-state: the table the record sat
    on was the tenant scope and the retired noun, in that order, under the
    project's namespace prefix. A rename of any part of that moves this with it.
    """
    migration = MigrationLoader(connection).get_migration("pricing",
                                                          THE_DELETION)
    was = the_state_before(migration).models[
        ("pricing", "tenantmarkup")].options["db_table"]
    return was.removeprefix("ubb_tenant_") + "."


def the_acts_that_ceased():
    prefix = the_retired_record()
    return tuple(prefix + verb for verb in THE_VERBS_THAT_CEASED)


@pytest.mark.django_db
def test_the_derivation_reaches_two_names_that_look_like_actions():
    """The vacuity guard for everything below it.

    A derivation that came back empty, or with a prefix that stopped being the
    retired noun, would make every case below true by iterating nothing — the
    exact shape a derived fixture has to be defended against.
    """
    names = the_acts_that_ceased()

    assert len(names) == 2
    for name in names:
        noun, _, verb = name.partition(".")
        assert noun and verb, name
        assert verb in THE_VERBS_THAT_CEASED, name


@pytest.mark.django_db
def test_the_derived_noun_is_the_one_the_records_own_columns_were_named_for():
    """The POSITIVE control, and the reason it is needed.

    Every case below asserts an ABSENCE, and a derivation that quietly answered
    the wrong noun would make all of them true against a registry that still
    held the retired names. This ties the derivation to a SECOND independent
    fact in the same from-state: the record's percentage column led with the
    same noun. A `removeprefix` that failed to strip the tenant scope would
    answer `tenant_markup`, which is not the leading segment of any column on
    that model, and this goes red.

    ⚠ It is a corroboration rather than the whole proof. The other half is
    measured: pointing `test_no_surviving_action_names_the_retired_record` at
    `"tenant_default_" + the derived noun` turns it RED naming the live rung's
    two actions — which can only happen if the derived noun really is the
    trailing segment of that rung's own name.
    """
    noun = the_retired_record().rstrip(".")
    migration = MigrationLoader(connection).get_migration("pricing",
                                                          THE_DELETION)
    columns = dict(the_state_before(migration).models[
        ("pricing", "tenantmarkup")].fields)

    assert noun
    assert [name for name in columns if name.startswith(noun + "_")]


@pytest.mark.django_db
def test_the_registry_knows_neither_of_them():
    from apps.platform.audit.actions import AUDIT_ACTIONS, is_registered_action

    for name in the_acts_that_ceased():
        assert name not in AUDIT_ACTIONS, name
        assert not is_registered_action(name), name


@pytest.mark.django_db
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
            record(action=name, tenant_id=tenant.id, resource_type="markup")


@pytest.mark.django_db
def test_no_surviving_action_names_the_retired_record():
    """The stronger form, over the whole registry.

    Asserting two names are absent says nothing about a third somebody adds
    later under the same retired noun — which is the shape a by-name check
    always has. ⚠ The prefix is matched at the START of the name rather than
    anywhere in it: the rung that replaced this record is
    `tenant_default_markup.*`, whose noun ENDS with the retired one, so a
    substring test would report the live replacement as a survivor and this
    case would fail on the very thing it exists to permit.
    """
    from apps.platform.audit.actions import AUDIT_ACTIONS

    surviving = [name for name in AUDIT_ACTIONS
                 if name.startswith(the_retired_record())]

    assert surviving == []


@pytest.mark.django_db
def test_the_replacement_rung_is_registered_under_its_own_pair():
    """The other side of the case above, so "nothing survives" cannot be read
    as "markup governance stopped being recorded".

    Two acts on the record that replaced this one, registered and distinct —
    which is what makes the deletion above a deletion rather than a silent loss
    of the ledger's account of who decided what a customer is charged.
    """
    from apps.platform.audit.actions import is_registered_action

    assert is_registered_action("tenant_default_markup.declared")
    assert is_registered_action("tenant_default_markup.withdrawn")


@pytest.mark.django_db
def test_the_record_is_not_in_the_model_registry_at_all():
    """The model, asked of Django rather than of an import.

    An `ImportError` case would pass against a module that merely stopped
    exporting the class; the app registry is what the ORM, the admin and the
    sandbox reset all read.
    """
    labels = {model._meta.object_name
              for model in django_apps.get_app_config("pricing").get_models()}

    assert "TenantMarkup" not in labels


@pytest.mark.django_db
def test_the_table_is_gone_from_the_database():
    """The migration ran, asked of the database rather than of the graph."""
    was = the_state_before(
        MigrationLoader(connection).get_migration("pricing", THE_DELETION)
    ).models[("pricing", "tenantmarkup")].options["db_table"]

    assert was not in connection.introspection.table_names()


@pytest.mark.django_db
def test_the_sandbox_reset_no_longer_names_the_record_as_configuration():
    """A label for a model that does not exist would fail the reset's own
    resolve, and the only test over that set asks whether each label RESOLVES —
    so it would catch this one. What it would NOT catch is the inverse, which
    is why #357's rung is asserted present beside it.
    """
    from apps.platform.tenants.tasks import CONFIG_MODEL_LABELS

    assert "pricing.TenantMarkup" not in CONFIG_MODEL_LABELS
    assert "pricing.TenantDefaultMarkup" in CONFIG_MODEL_LABELS


@pytest.mark.django_db
def test_the_plan_carries_no_markup_column_and_still_carries_its_book():
    """The kernel half. Both columns go, and the reference that replaced them
    stays — asserted together, because "the plan has no markup" read alone is
    equally true of a plan that has lost its pricing entirely.
    """
    columns = {field.name for field in Plan._meta.get_fields()}

    assert "markup_percentage_micros" not in columns
    assert "fixed_uplift_micros" not in columns
    assert "pricing_book" in columns


@pytest.mark.django_db
def test_a_plan_created_today_supplies_no_markup_rung():
    """The behaviour behind the column's absence, through the production door.

    Before this commit a plan ALWAYS supplied a rung, because the percentage
    defaulted to zero — so "the tenant has said nothing about what to charge"
    was served as "the tenant said charge cost", which settles a price nobody
    stated. The ladder's answer for a customer on a plan is now the tenant's own
    declaration or nothing at all.
    """
    from apps.metering.pricing.services.markup_service import MarkupService
    from apps.platform.plans.services import PlanService

    tenant = Tenant.objects.create(name="Plans",
                                   products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    PlanService.assign(tenant, customer, a_plan(tenant=tenant, key="lite"))

    assert MarkupService.resolve(tenant) is None


@pytest.mark.django_db
def test_the_read_contract_offers_no_markup_for_a_customers_plan():
    """The channel metering read that rung through, asked of the module rather
    than of a caller: a product may only reach the plan catalog through this
    contract (ADR-001), so its absence here is the absence of the rung.
    """
    from apps.platform.plans import queries

    assert not hasattr(queries, "get_plan_markup_for_customer")
    assert hasattr(queries, "get_pricing_book_for_customer")
