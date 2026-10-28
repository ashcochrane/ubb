"""A sandbox reset keeps what it promises and never fails half-way (#593, #595;
W5 ruling 14).

Every row a reset meets here was produced the way a tenant produces it —
through the sandbox's own test key and its routes — because both defects hid
behind hand-built fixtures no route produces (#593's fixture named no supplier,
#595's declared no kind of work). The one exception is filing a Measurement
under a Measurement Concept: no route does that, so it is written to the row,
and said so where it happens.

- #595: a reset that KEEPS configuration keeps the kinds of work and the
  Grouping Fields they require.
- #593: a reset that WIPES configuration completes for an Event Type that names a
  supplier and a category and declares a quantity filed under a concept — the
  Event Type is taken after the rules and held names that point at it, then its
  supplier, category and concept.
- Ruling 14: either reset keeps the tenant's team — its members and invitations
  are access state, not configuration.
"""
import pytest
from django.test import Client

from api.v1.tests._helpers import (
    EVENT, INPUT_TOKENS, KIND, PROVIDER, BlueprintRoutes)
from apps.platform.event_types.models import (
    EventCategory, EventType, Measurement, MeasurementConcept, Provider)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.membership.models import Invitation, Member
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.tenants.tasks import reset_sandbox_tenant_sync
from apps.platform.work.models import TaskType

CATEGORY = "assistant"
TEAMMATE = "teammate@example.com"

#: What the tenant declared, each read back by the model that holds it.
DECLARED = (TaskType, GroupingField, Provider, EventCategory, EventType,
            MeasurementConcept)


@pytest.mark.django_db
class TestAResetKeepsWhatItPromises(BlueprintRoutes):

    def setup_method(self):
        self.live = Tenant.objects.create(name="Live", products=["metering"])
        self.tenant = get_or_create_sandbox(self.live)
        _, self.raw_key = TenantApiKey.create_key(self.live, is_test=True)
        self.client = Client()
        self._declare_everything()

    def _declare_everything(self):
        # A kind of work requiring a Grouping Field (#595).
        self._grouping_fields(("environment", "task"))
        self._kinds({"key": KIND, "uncapped": True,
                     "required_grouping_fields": ["environment"]})
        # An Event Type naming a supplier and a category (#593).
        self._call("post", "/api/v1/providers", {"key": PROVIDER})
        self._call("post", "/api/v1/event-categories", {"key": CATEGORY})
        self._call("post", "/api/v1/event-types",
                   {"key": EVENT, "costing_method": "calculated",
                    "provider_key": PROVIDER, "category_key": CATEGORY})
        self._call("put", f"/api/v1/event-types/{EVENT}/measurements/"
                          f"input_tokens", INPUT_TOKENS)
        # ⚠ NO ROUTE FILES A QUANTITY UNDER A MEASUREMENT CONCEPT, so this one
        # step is written to the rows — before publishing, as a declaration
        # would carry it.
        concept = MeasurementConcept.objects.create(tenant=self.tenant,
                                                    key="input_size")
        Measurement.objects.filter(event_type__tenant=self.tenant).update(
            concept=concept)
        self._publish(EVENT)
        # The team: an invitation, which brings a pending member with it.
        self._call("post", "/api/v1/tenant/invitations",
                   {"email": TEAMMATE, "role": "admin"})

    def _held(self, model):
        manager = getattr(model, "all_objects", model._base_manager)
        if model is Measurement:
            return manager.filter(event_type__tenant=self.tenant).count()
        return manager.filter(tenant=self.tenant).count()

    def _the_team(self):
        return (Member.objects.filter(tenant=self.tenant, email=TEAMMATE).count(),
                Invitation.objects.filter(tenant=self.tenant,
                                          email=TEAMMATE).count())

    def test_the_fixture_holds_every_shape_it_names(self):
        """The premise, asserted: a red case below is about the reset."""
        assert {model.__name__: self._held(model) for model in DECLARED} == {
            model.__name__: 1 for model in DECLARED}
        event_type = EventType.objects.get(tenant=self.tenant, key=EVENT)
        assert event_type.provider is not None
        assert event_type.category is not None
        assert self._held(Measurement) == 1
        assert Measurement.objects.get(
            event_type=event_type).concept is not None
        assert self._the_team() == (1, 1)

    def test_keeping_configuration_keeps_the_kinds_of_work_and_their_fields(self):
        """#595."""
        result = reset_sandbox_tenant_sync(self.tenant.id, keep_config=True)

        assert result["status"] == "completed"
        for model in DECLARED:
            assert self._held(model) == 1, model.__name__
        assert self._held(Measurement) == 1
        assert self._the_team() == (1, 1)

    def test_wiping_configuration_completes_with_a_supplied_event_type(self):
        """#593: it used to raise, refused by the Event Type's PROTECT on its
        supplier, and leave the sandbox inactive."""
        result = reset_sandbox_tenant_sync(self.tenant.id, keep_config=False)

        assert result["status"] == "completed"
        for model in (*DECLARED, Measurement):
            assert self._held(model) == 0, model.__name__
        self.tenant.refresh_from_db()
        assert self.tenant.is_active

    def test_either_reset_keeps_the_team(self):
        """Ruling 14: members and invitations are access state."""
        reset_sandbox_tenant_sync(self.tenant.id, keep_config=False)
        assert self._the_team() == (1, 1)

        reset_sandbox_tenant_sync(self.tenant.id, keep_config=True)
        assert self._the_team() == (1, 1)
