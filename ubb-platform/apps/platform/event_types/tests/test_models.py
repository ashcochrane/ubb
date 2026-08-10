"""The two optional satellites, exercised against a real database (#261).

What is worth testing about a record this small is not that Django can save it.
It is the three claims the ticket makes about it that a smaller design would
quietly break: retirement leaves the past readable, identity survives a rename,
and neither satellite is required by anything.

The structural claims — no hierarchy, no effective-dating, no monetary reach,
nothing behavioural wired — are not here. They are properties of the tree rather
than of a row, so they live next door in
``apps/platform/tests/test_event_type_satellite_invariants.py``, where they can
be classified through a real walker with a negative control.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.platform.event_types.models import EventCategory, Provider
from apps.platform.tenants.models import Tenant


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


@pytest.mark.django_db
class TestProviderIsTenantScoped:
    def test_key_unique_per_tenant(self):
        t = _tenant()
        Provider.objects.create(tenant=t, key="acme-inference")
        with pytest.raises(IntegrityError):
            Provider.objects.create(tenant=t, key="acme-inference")

    def test_same_key_allowed_across_tenants(self):
        a, b = _tenant("A"), _tenant("B")
        Provider.objects.create(tenant=a, key="acme-inference")
        Provider.objects.create(tenant=b, key="acme-inference")
        assert Provider.objects.count() == 2


@pytest.mark.django_db
class TestProviderIsRetiredNeverDeleted:
    """Retirement stops new use and leaves historical attribution resolvable."""

    def test_a_retired_provider_is_still_resolvable_by_its_identity(self):
        t = _tenant()
        p = Provider.objects.create(tenant=t, key="acme-inference")
        identity = p.pk

        p.retired_at = timezone.now()
        p.save(update_fields=["retired_at"])

        # The attribution a historical posting holds is this identity. A delete
        # would have made the line below raise, and the report that reads it
        # would be missing a supplier it definitely had.
        still_there = Provider.objects.get(pk=identity)
        assert still_there.key == "acme-inference"
        assert still_there.retired_at is not None

    def test_retirement_is_readable_as_a_state_without_hiding_the_row(self):
        """The two readings retirement has to keep separate.

        "Which may a new declaration choose" is a filter, and "which existed"
        is the unfiltered manager. There is no ``selectable()`` helper on the
        model and deliberately so — the filter belongs to the ticket that first
        attaches a supplier to something, which is the ticket that can also
        test that a retired one was refused. What this pins is that both
        readings are available and that they differ.
        """
        t = _tenant()
        live = Provider.objects.create(tenant=t, key="acme-inference")
        Provider.objects.create(tenant=t, key="legacy-vendor",
                                retired_at=timezone.now())

        choosable = set(Provider.objects.filter(retired_at__isnull=True)
                        .values_list("pk", flat=True))
        assert choosable == {live.pk}
        # ...and the unfiltered manager still sees both, which is the half that
        # keeps the past readable.
        assert Provider.objects.count() == 2

    def test_retiring_is_not_deleting_even_when_it_is_the_tenants_only_supplier(self):
        t = _tenant()
        p = Provider.objects.create(tenant=t, key="acme-inference")
        p.retired_at = timezone.now() - timedelta(days=90)
        p.save(update_fields=["retired_at"])

        assert Provider.objects.filter(tenant=t).count() == 1
        assert Provider.objects.filter(tenant=t, retired_at__isnull=True).count() == 0


@pytest.mark.django_db
class TestSupplierCostResolutionKeysOnIdentity:
    """Why the supplier is a record and not a string on the Event Type key.

    The absence half of this claim — that no code path parses a supplier name
    out of an Event Type key — is a property of the tree, and is asserted in
    ``test_event_type_satellite_invariants.py`` with its own negative control.
    This is the positive half: identity is stable under exactly the change that
    would break name-parsing.
    """

    def test_a_freed_spelling_does_not_take_the_old_supplier_with_it(self):
        """The failure a name-parsing resolver produces, made concrete.

        A tenant renames their supplier and later reuses the freed handle for a
        different one — an ordinary sequence, not a contrived one. A resolver
        that had parsed "acme" out of an Event Type key would now attribute the
        first supplier's historical cost to the second. Identity does not move.
        """
        t = _tenant()
        original = Provider.objects.create(tenant=t, key="acme")
        # What a historical posting holds.
        attribution = original.pk

        original.key = "acme-ai"
        original.save(update_fields=["key"])
        reused = Provider.objects.create(tenant=t, key="acme")

        # The spelling now answers with a supplier that did not exist when the
        # posting was written...
        assert Provider.objects.get(tenant=t, key="acme").pk == reused.pk
        # ...and the identity still answers with the one that did.
        assert Provider.objects.get(pk=attribution).pk == original.pk
        assert attribution != reused.pk

    def test_identity_is_not_the_key(self):
        """Two tenants may spell the same supplier the same way.

        So the key is not an identity even before anyone renames one, and a
        resolver keyed on the spelling would have to guess which tenant's
        supplier it had found.
        """
        a, b = _tenant("A"), _tenant("B")
        pa = Provider.objects.create(tenant=a, key="acme-inference")
        pb = Provider.objects.create(tenant=b, key="acme-inference")
        assert pa.pk != pb.pk


@pytest.mark.django_db
class TestInternalWorkNeedsNoSupplier:
    """A tenant metering its own internal work invents nothing."""

    def test_a_tenant_may_declare_no_supplier_at_all(self):
        t = _tenant()
        assert Provider.objects.filter(tenant=t).count() == 0
        # Nothing on the tenant demands one, and nothing created one on the way
        # in. A fictitious row here would be a defect, not a convenience.
        assert Provider.objects.filter(tenant=t).exists() is False

    def test_no_provider_is_created_as_a_side_effect_of_creating_a_tenant(self):
        before = Provider.objects.count()
        _tenant("fresh")
        assert Provider.objects.count() == before


@pytest.mark.django_db
class TestEventCategory:
    def test_key_unique_per_tenant(self):
        t = _tenant()
        EventCategory.objects.create(tenant=t, key="inference")
        with pytest.raises(IntegrityError):
            EventCategory.objects.create(tenant=t, key="inference")

    def test_same_key_allowed_across_tenants(self):
        a, b = _tenant("A"), _tenant("B")
        EventCategory.objects.create(tenant=a, key="inference")
        EventCategory.objects.create(tenant=b, key="inference")
        assert EventCategory.objects.count() == 2

    def test_a_tenant_may_declare_none(self):
        t = _tenant()
        assert EventCategory.objects.filter(tenant=t).count() == 0
