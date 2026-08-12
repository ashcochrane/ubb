"""The projection behind the published grouping-field object (#277, ticket 20).

`grouping_fields_for` is the only thing that turns a posting's ten physical slot
columns into the object a caller reads. The endpoint tests in
`api/v1/tests/test_grouping_values_on_the_contract.py` prove the two responses
carry it; this file proves the projection itself, including the three cases no
response test reaches — the tenant with nothing declared, the slot holding a
value no declaration names, and the query count.
"""
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.metering.usage.grouping import grouping_fields_for
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.grouping_fields.queries import keys_by_slot
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestKeysBySlot:
    def test_it_is_the_inverse_of_the_slot_map(self):
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1",
                                     scope="event")
        GroupingField.objects.create(tenant=t, key="model_variant",
                                     slot="grouping_field_10", scope="event")
        assert keys_by_slot(t.id) == {"grouping_field_1": "region",
                                      "grouping_field_10": "model_variant"}

    def test_a_retired_declaration_still_names_its_slot(self):
        """Retirement blocks new VALUES, not reads (D8). A posting recorded
        before a field was retired must still say what its value MEANS —
        dropping the key here would silently un-name historical rows."""
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1",
                                     scope="event", retired_at="2026-01-01T00:00:00Z")
        assert keys_by_slot(t.id) == {"grouping_field_1": "region"}

    def test_another_tenants_declarations_are_not_visible(self):
        mine = Tenant.objects.create(name="mine")
        theirs = Tenant.objects.create(name="theirs")
        GroupingField.objects.create(tenant=theirs, key="region",
                                     slot="grouping_field_1", scope="event")
        assert keys_by_slot(mine.id) == {}


@pytest.mark.django_db
class TestGroupingFieldsFor:
    def _posting(self, tenant, **slots):
        # Built with only the columns this file is about. The correlation
        # identifier every other posting fixture sets is a retired word under
        # slice 5's ledger entry, and its recorded extent may not grow — the
        # column is blank-defaulted, and nothing here reads it.
        c = Customer.objects.create(tenant=tenant, external_id="c1")
        return Posting.objects.create(
            tenant=tenant, customer=c, idempotency_key="k1",
            provider="openai", event_type="completion", **slots)

    def test_each_set_slot_appears_under_the_tenants_own_key(self):
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1",
                                     scope="event")
        GroupingField.objects.create(tenant=t, key="model_variant",
                                     slot="grouping_field_4", scope="event")
        p = self._posting(t, grouping_field_1="eu-west-1",
                          grouping_field_4="flash-4.0-standard")
        assert grouping_fields_for(p) == {"region": "eu-west-1",
                                          "model_variant": "flash-4.0-standard"}

    def test_an_unset_slot_is_omitted_rather_than_carried_as_empty(self):
        """"" is the column's "not set", and publishing it would make an
        integrator write `if value != ""` against a key they declared and never
        used. The object names what the posting HAS."""
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1",
                                     scope="event")
        GroupingField.objects.create(tenant=t, key="unused", slot="grouping_field_2",
                                     scope="event")
        p = self._posting(t, grouping_field_1="eu-west-1")
        assert grouping_fields_for(p) == {"region": "eu-west-1"}

    def test_the_tenth_slot_is_reachable(self):
        """#276 widened the slots to ten and the published shape must reach all
        of them — the old per-slot properties stopped at three."""
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="tier", slot="grouping_field_10",
                                     scope="event")
        p = self._posting(t, grouping_field_10="enterprise")
        assert grouping_fields_for(p) == {"tier": "enterprise"}

    def test_a_value_no_declaration_names_is_omitted(self):
        """A slot can hold a value the registry cannot name — a declaration
        deleted outright rather than retired. There is no key to publish it
        under, so it is omitted rather than published under its physical slot:
        exposing the slot here is exactly what this ticket removed everywhere
        else, and it would arrive under a name the tenant never chose.
        """
        t = Tenant.objects.create(name="T")
        p = self._posting(t, grouping_field_1="orphaned")
        assert grouping_fields_for(p) == {}

    def test_a_posting_with_no_grouping_values_costs_no_query(self):
        """The record-usage response carries this object, so the projection
        sits on the hottest write path in the system. A tenant that declares no
        grouping fields — every tenant, on day one — must not pay a registry
        read per posting to be told there is nothing to say.
        """
        t = Tenant.objects.create(name="T")
        p = self._posting(t)
        with CaptureQueriesContext(connection) as captured:
            assert grouping_fields_for(p) == {}
        assert len(captured) == 0

    def test_a_posting_with_grouping_values_costs_exactly_one_query(self):
        t = Tenant.objects.create(name="T")
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1",
                                     scope="event")
        p = self._posting(t, grouping_field_1="eu-west-1")
        with CaptureQueriesContext(connection) as captured:
            assert grouping_fields_for(p) == {"region": "eu-west-1"}
        assert len(captured) == 1
