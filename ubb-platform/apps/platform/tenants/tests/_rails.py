"""Payment-rail activation as a test ASKS for it (G27; the owner's §0.4 E).

`prepaid` and `postpaid` may not be entered before the Stripe rail is activated
for the tenant's environment (ADR-0008 §6), and the database refuses a tenant
row that tries. A test that builds a money-mode tenant therefore needs the
activation — and must SAY so, because a helper that quietly made every fixture
rail-ready would make the invariant invisible to the very suite meant to catch
its loss.

So the capability is opt-in and named at the test that uses it:

- a `TestCase` class lists `RailActivated` among its bases;
- a pytest function requests the `rail_activated` fixture (`conftest.py`);
- anything else calls `activate_the_rail` itself.

A test proving the refusal uses none of these, and needs nothing else: no
default activation exists anywhere — not in a fixture, not in a migration, and
not in `seed_dev_data`, which records no evidence of its own.

The evidence written here says it is a test's, so a row of it reaching a real
database would say plainly what it is.
"""
from django.utils import timezone

from apps.platform.tenants.models import PaymentRailActivation, TENANT_MONEY_RAIL
from core.vocabulary import (
    PAYMENT_RAIL_ENVIRONMENT_LIVE,
    PAYMENT_RAIL_ENVIRONMENT_TEST,
)

#: Both environments: a class that asks for the rail can build a live tenant
#: in a money mode and its sandbox.
BOTH_ENVIRONMENTS = (PAYMENT_RAIL_ENVIRONMENT_LIVE, PAYMENT_RAIL_ENVIRONMENT_TEST)


def activate_the_rail(*environments, enabled=True):
    """Record the tenant money rail's activation in each environment named.

    Idempotent per environment — an activation is one row per rail and
    environment, and its evidence is frozen, so a second ask returns the first.
    """
    activations = []
    for environment in environments or BOTH_ENVIRONMENTS:
        activation, _ = PaymentRailActivation.objects.get_or_create(
            rail=TENANT_MONEY_RAIL, environment=environment,
            defaults={
                "activated_at": timezone.now(),
                "approved_by": "a test that asked for the rail",
                "evidence": "test fixture: activation requested by name (G27)",
                "enabled": enabled,
            })
        activations.append(activation)
    return activations


class RailActivated:
    """A test-case mixin: this class asks for the rail, in both environments.

    Two hooks, because Django has two kinds of test case. A `TestCase`'s
    class-level data is built in `setUpTestData`, so the rail is activated
    there first — a class that defines its own calls
    `super().setUpTestData()` first, the order every Django test-data hook
    already expects. A `TransactionTestCase` has no class-level data and
    empties the database after every test, so the rail is activated again in
    `_fixture_setup`, which Django runs before each test's `setUp` once the
    database is ready (an idempotent read for a `TestCase`).
    """

    @classmethod
    def setUpTestData(cls):
        activate_the_rail()
        super().setUpTestData()

    @classmethod
    def _fixture_setup(cls):
        super()._fixture_setup()
        activate_the_rail()
