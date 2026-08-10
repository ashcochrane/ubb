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

    def test_retirement_removes_it_from_what_a_new_declaration_may_select(self):
        t = _tenant()
        live = Provider.objects.create(tenant=t, key="acme-inference")
        retired = Provider.objects.create(tenant=t, key="legacy-vendor",
                                          retired_at=timezone.now())

        selectable = set(Provider.objects.selectable().values_list("pk", flat=True))
        assert selectable == {live.pk}
        # ...and the unfiltered manager still sees both, which is the half that
        # keeps the past readable.
        assert Provider.objects.count() == 2

    def test_retiring_is_not_deleting_even_when_it_is_the_tenants_only_supplier(self):
        t = _tenant()
        p = Provider.objects.create(tenant=t, key="acme-inference")
        p.retired_at = timezone.now() - timedelta(days=90)
        p.save(update_fields=["retired_at"])

        assert Provider.objects.filter(tenant=t).count() == 1
        assert Provider.objects.selectable().filter(tenant=t).count() == 0


@pytest.mark.django_db
class TestSupplierCostResolutionKeysOnIdentity:
    """Why the supplier is a record and not a string on the Event Type key.

    The absence half of this claim — that no code path parses a supplier name
    out of an Event Type key — is a property of the tree, and is asserted in
    ``test_event_type_satellite_invariants.py`` with its own negative control.
    This is the positive half: identity is stable under exactly the change that
    would break name-parsing.
    """

    def test_identity_survives_a_key_rename(self):
        t = _tenant()
        p = Provider.objects.create(tenant=t, key="acme-inference")
        identity = p.pk

        # A tenant corrects their own handle. Nothing about which supplier this
        # is has changed.
        p.key = "acme-ai"
        p.save(update_fields=["key"])

        resolved = Provider.objects.get(pk=identity)
        assert resolved.pk == identity
        assert resolved.key == "acme-ai"
        # A resolver that had parsed "acme-inference" out of an Event Type key
        # would now be attributing this tenant's cost to a supplier that no
        # longer exists under that name.
        assert not Provider.objects.filter(tenant=t, key="acme-inference").exists()

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
