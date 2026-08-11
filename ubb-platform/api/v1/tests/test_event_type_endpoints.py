"""The Event Type catalogue's tenant surface (#267).

What is asserted here is **agreement between the caller and the declaration**,
never how a handler is written: a tenant declares something, and what comes back
— and what the next read says — is what a generated integration would be built
against.

The rules themselves belong to the models and are tested there. This module
asserts the three things only a route can be wrong about:

* the declaration a caller gets back is the one they made, parts and all;
* a refusal reaches them as a refusal, with the field named, rather than as a
  500 or a silent success;
* the lifecycle survives the round trip — a change through the API un-publishes
  exactly as a change through the model does, because the un-publishing is the
  model's and a handler that routed around it would be the one bug this surface
  can introduce on its own.
"""
import json

import pytest
from django.test import Client

from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.models import (
    EventCategory, EventType, Measurement, Provider, ReportedCostMapping,
)
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestEventTypeCatalogueSurface:
    def setup_method(self):
        # products=[...] is REQUIRED — every route here is gated by
        # _product_check, so a tenant without "metering" gets 403, not 422.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    # -- helpers ---------------------------------------------------------

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def _post(self, path, data=None):
        return self.client.post(path, data=json.dumps(data or {}),
                                content_type="application/json", **self._auth())

    def _put(self, path, data):
        return self.client.put(path, data=json.dumps(data),
                               content_type="application/json", **self._auth())

    def _patch(self, path, data):
        return self.client.patch(path, data=json.dumps(data),
                                 content_type="application/json", **self._auth())

    def _delete(self, path):
        return self.client.delete(path, **self._auth())

    def _declare_calculated(self, key="chat.completion"):
        return self._post("/api/v1/event-types",
                          {"key": key, "costing_method": "calculated"})

    # -- suppliers -------------------------------------------------------

    def test_a_declared_supplier_comes_back_and_is_listed(self):
        created = self._post("/api/v1/providers", {"key": "openai"})
        assert created.status_code == 201
        assert created.json() == {"key": "openai", "retired_at": None}

        listed = self._get("/api/v1/providers")
        assert listed.status_code == 200
        assert listed.json()["providers"] == [{"key": "openai",
                                               "retired_at": None}]

    def test_a_second_supplier_with_the_same_key_is_a_conflict(self):
        self._post("/api/v1/providers", {"key": "openai"})
        again = self._post("/api/v1/providers", {"key": "openai"})

        assert again.status_code == 409
        assert Provider.objects.filter(tenant=self.tenant).count() == 1

    def test_a_supplier_is_retired_rather_than_deleted_and_stays_readable(self):
        """The rule the model states, asserted through the surface that would
        otherwise be the easiest place to break it: there is no DELETE, and a
        retired supplier is still listed, because retirement governs what may
        be ATTACHED next and never what may be READ."""
        self._post("/api/v1/providers", {"key": "openai"})

        retired = self._patch("/api/v1/providers/openai", {"retired": True})
        assert retired.status_code == 200
        assert retired.json()["retired_at"] is not None

        assert self._delete("/api/v1/providers/openai").status_code == 405
        assert [p["key"] for p in
                self._get("/api/v1/providers").json()["providers"]] == ["openai"]

    def test_retiring_is_a_two_way_switch(self):
        self._post("/api/v1/providers", {"key": "openai"})
        self._patch("/api/v1/providers/openai", {"retired": True})

        revived = self._patch("/api/v1/providers/openai", {"retired": False})

        assert revived.status_code == 200
        assert revived.json()["retired_at"] is None

    def test_renaming_a_supplier_keeps_its_identity(self):
        """A tenant's handle is theirs to correct, and nothing downstream holds
        it — which is the whole reason supplier cost resolution keys on the
        record rather than on the key."""
        self._post("/api/v1/providers", {"key": "opanai"})
        identity = Provider.objects.get(tenant=self.tenant).id

        renamed = self._patch("/api/v1/providers/opanai", {"key": "openai"})

        assert renamed.status_code == 200
        assert renamed.json()["key"] == "openai"
        assert Provider.objects.get(tenant=self.tenant).id == identity

    def test_a_supplier_from_another_tenant_is_not_found(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        Provider.objects.create(tenant=other, key="openai")

        assert self._patch("/api/v1/providers/openai",
                           {"key": "x"}).status_code == 404

    # -- categories ------------------------------------------------------

    def test_a_category_is_declared_listed_and_withdrawn(self):
        assert self._post("/api/v1/event-categories",
                          {"key": "inference"}).status_code == 201
        assert self._get("/api/v1/event-categories").json()[
            "event_categories"] == [{"key": "inference"}]
        assert self._delete(
            "/api/v1/event-categories/inference").status_code == 204
        assert not EventCategory.objects.filter(tenant=self.tenant).exists()

    def test_a_category_in_use_is_refused_rather_than_erroring(self):
        """PROTECT would otherwise surface as a 500. The refusal names how many
        declarations still group under it, because the repair is to move them."""
        self._post("/api/v1/event-categories", {"key": "inference"})
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "calculated",
                                           "category_key": "inference"})

        refused = self._delete("/api/v1/event-categories/inference")

        assert refused.status_code == 409
        assert EventCategory.objects.filter(tenant=self.tenant).exists()

    # -- Event Types -----------------------------------------------------

    def test_a_declaration_arrives_as_a_draft_and_reads_back_whole(self):
        created = self._declare_calculated()

        assert created.status_code == 201
        body = created.json()
        assert body["key"] == "chat.completion"
        assert body["costing_method"] == "calculated"
        assert body["declaration_status"] == "draft"
        assert body["published_revision"] == 0
        assert body["published_at"] is None
        assert body["publication_blockers"] == []
        assert body["measurements"] == []
        assert body["reported_cost_mapping"] is None

        assert self._get("/api/v1/event-types/chat.completion").json() == body

    def test_a_costing_method_outside_the_value_set_is_refused(self):
        refused = self._post("/api/v1/event-types",
                             {"key": "chat.completion",
                              "costing_method": "guessed"})

        assert refused.status_code == 422
        assert "costing_method" in refused.json()["detail"]
        assert not EventType.objects.filter(tenant=self.tenant).exists()

    def test_naming_a_supplier_that_does_not_exist_is_not_an_auto_registration(
            self):
        """A key UBB has never seen is never registered by naming it. A typo
        that registered itself would become permanent billing vocabulary."""
        refused = self._post("/api/v1/event-types",
                             {"key": "chat.completion",
                              "costing_method": "calculated",
                              "provider_key": "opanai"})

        assert refused.status_code == 404
        assert not Provider.objects.filter(tenant=self.tenant).exists()
        assert not EventType.objects.filter(tenant=self.tenant).exists()

    def test_an_absent_field_is_untouched_and_an_empty_one_detaches(self):
        self._post("/api/v1/providers", {"key": "openai"})
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "calculated",
                                           "provider_key": "openai"})

        untouched = self._patch("/api/v1/event-types/chat.completion",
                                {"source_shape_id": "openai.responses.python.v1"})
        assert untouched.json()["provider_key"] == "openai"

        detached = self._patch("/api/v1/event-types/chat.completion",
                               {"provider_key": ""})
        assert detached.json()["provider_key"] is None

    def test_publishing_pins_the_declaration_and_a_change_returns_it_to_draft(
            self):
        """The lifecycle, through the surface. The un-publishing is the model's
        rule and this proves the route does not route around it — which is the
        one way this surface could break a rule it does not own."""
        self._declare_calculated()

        published = self._post("/api/v1/event-types/chat.completion/publish")
        assert published.status_code == 200
        assert published.json()["declaration_status"] == "published"
        assert published.json()["published_revision"] == 1
        assert published.json()["published_at"] is not None

        revised = self._patch("/api/v1/event-types/chat.completion",
                              {"source_shape_id": "openai.responses.python.v1"})
        assert revised.json()["declaration_status"] == "draft"
        assert revised.json()["published_revision"] == 1

    def test_a_reported_declaration_cannot_publish_without_its_mapping(self):
        """The blocker is served on the declaration AND enforced at publication,
        so a caller can see what is missing before they are refused it."""
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "reported"})

        assert self._get("/api/v1/event-types/chat.completion").json()[
            "publication_blockers"] == ["reported_cost_mapping"]

        refused = self._post("/api/v1/event-types/chat.completion/publish")
        assert refused.status_code == 409
        assert "reported_cost_mapping" in refused.json()["detail"]
        assert EventType.objects.get(
            tenant=self.tenant).declaration_status == "draft"

    def test_declaring_the_mapping_clears_the_blocker_and_publication_follows(
            self):
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "reported"})
        declared = self._put(
            "/api/v1/event-types/chat.completion/reported-cost-mapping",
            {"source_kind": "provider_response",
             "amount_representation": "micros",
             "source_path": ["usage", "cost_micros"], "currency": "usd"})

        assert declared.status_code == 201
        assert self._get("/api/v1/event-types/chat.completion").json()[
            "publication_blockers"] == []
        assert self._post(
            "/api/v1/event-types/chat.completion/publish").status_code == 200

    # -- declared quantities ---------------------------------------------

    def test_a_declared_quantity_reads_back_on_its_own_and_on_the_parent(self):
        self._declare_calculated()

        declared = self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "token",
             "required_for_costing": True, "source_kind": "provider_response",
             "source_path": ["usage", "prompt_tokens"]})

        assert declared.status_code == 201
        assert declared.json()["code"] == "input_tokens"
        assert declared.json()["advisories"] == []
        assert self._get(
            "/api/v1/event-types/chat.completion/measurements").json()[
                "measurements"] == [declared.json()]
        assert self._get("/api/v1/event-types/chat.completion").json()[
            "measurements"] == [declared.json()]

    def test_redeclaring_the_same_code_replaces_rather_than_duplicates(self):
        self._declare_calculated()
        path = "/api/v1/event-types/chat.completion/measurements/input_tokens"
        body = {"value_type": "integer", "unit": "token",
                "source_kind": "provider_response",
                "source_path": ["usage", "prompt_tokens"]}
        self._put(path, body)

        again = self._put(path, {**body, "required_for_costing": True})

        assert again.status_code == 200
        assert Measurement.objects.filter(
            event_type__tenant=self.tenant).count() == 1
        assert again.json()["required_for_costing"] is True

    def test_the_same_code_on_two_event_types_is_two_declarations(self):
        """A tenant's two integrations never have to agree about spelling to
        both be correct."""
        for key in ("gemini.generate", "openai.chat"):
            self._post("/api/v1/event-types",
                       {"key": key, "costing_method": "calculated"})
            self._put(f"/api/v1/event-types/{key}/measurements/input_tokens",
                      {"value_type": "integer", "unit": "token",
                       "source_kind": "provider_response",
                       "source_path": ["usage"]})

        assert Measurement.objects.filter(
            event_type__tenant=self.tenant, code="input_tokens").count() == 2

    def test_a_path_that_is_an_expression_is_refused_with_its_field_named(self):
        self._declare_calculated()

        refused = self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "token",
             "source_kind": "provider_response",
             "source_path": ["usage.prompt_tokens"]})

        assert refused.status_code == 422
        assert "source_path" in refused.json()["detail"]
        assert not Measurement.objects.filter(
            event_type__tenant=self.tenant).exists()

    def test_a_near_miss_on_the_unit_is_advised_and_never_corrected(self):
        """Advice is the entire product: UBB says the spelling looks like one
        it knows, accepts what was sent, and changes nothing."""
        self._declare_calculated()

        declared = self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "Tokens",
             "source_kind": "provider_response", "source_path": ["usage"]})

        assert declared.status_code == 201
        assert declared.json()["unit"] == "Tokens"
        assert any("Tokens" in advice
                   for advice in declared.json()["advisories"])

    def test_declaring_a_quantity_under_a_published_type_revises_it(self):
        self._declare_calculated()
        self._post("/api/v1/event-types/chat.completion/publish")

        self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "token",
             "source_kind": "provider_response", "source_path": ["usage"]})

        assert self._get("/api/v1/event-types/chat.completion").json()[
            "declaration_status"] == "draft"

    def test_withdrawing_a_quantity_revises_the_publication_too(self):
        self._declare_calculated()
        self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "token",
             "source_kind": "provider_response", "source_path": ["usage"]})
        self._post("/api/v1/event-types/chat.completion/publish")

        withdrawn = self._delete(
            "/api/v1/event-types/chat.completion/measurements/input_tokens")

        assert withdrawn.status_code == 204
        assert self._get("/api/v1/event-types/chat.completion").json()[
            "declaration_status"] == "draft"

    # -- the reported supplier cost --------------------------------------

    def test_the_mapping_serves_what_the_caller_must_supply(self):
        """The builder's half of `caller_supplied`, and the reason serving it
        is worth anything: a cost read from the response asks for nothing."""
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "reported"})

        supplied = self._put(
            "/api/v1/event-types/chat.completion/reported-cost-mapping",
            {"source_kind": "caller_supplied",
             "amount_representation": "major_units_decimal",
             "currency": "usd"})

        assert supplied.json()["required_runtime_parameters"] == \
            ["reported_cost"]

    def test_a_fixed_per_call_cost_is_refused_as_a_reported_one(self):
        """The narrowing lives at the model with its reasons; this asserts the
        refusal reaches the caller rather than becoming a 500."""
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "reported"})

        refused = self._put(
            "/api/v1/event-types/chat.completion/reported-cost-mapping",
            {"source_kind": "constant", "amount_representation": "micros",
             "currency": "usd"})

        assert refused.status_code == 422
        assert "source_kind" in refused.json()["detail"]
        assert not ReportedCostMapping.objects.exists()

    def test_the_mapping_is_read_and_withdrawn_on_its_own_path(self):
        self._post("/api/v1/event-types", {"key": "chat.completion",
                                           "costing_method": "reported"})
        path = "/api/v1/event-types/chat.completion/reported-cost-mapping"
        assert self._get(path).status_code == 404

        self._put(path, {"source_kind": "provider_response",
                         "amount_representation": "minor_units",
                         "source_path": ["usage", "cost"], "currency": "usd"})
        assert self._get(path).json()["amount_representation"] == "minor_units"

        assert self._delete(path).status_code == 204
        assert self._get(path).status_code == 404

    # -- the things every route on this surface must be ------------------

    def test_the_metering_product_gate_cannot_fire_today_and_is_kept_anyway(
            self):
        """A stated limit rather than a test that pretends otherwise.

        Every route here calls `ProductAccess("metering")`, and no tenant can
        currently fail it: `Tenant.clean` refuses to save a tenant whose
        products omit metering, so the refusal branch is unreachable from the
        outside. Asserting a 403 here would need a tenant the model forbids.

        The gate is kept because the two nearest neighbours have it for the
        same reason and being the one tenant surface with no product
        declaration would be the drift, not the tidy-up — and because the day
        metering stops being universal, this surface is already right. What is
        NOT acceptable is leaving that unsaid, so it is asserted from the other
        end: the constraint that makes the branch unreachable is proved to be
        the reason, so the day it is relaxed this test goes red and points at
        the gate that starts working.
        """
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError) as refused:
            Tenant.objects.create(name="No metering", products=["billing"])
        assert "metering" in str(refused.value)

    def test_an_unauthenticated_caller_reaches_none_of_it(self):
        for path in ("/api/v1/event-types", "/api/v1/providers",
                     "/api/v1/event-categories"):
            assert self.client.get(path).status_code == 401, path

    def test_one_tenants_catalogue_is_invisible_to_another(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        EventType.objects.create(tenant=other, key="theirs",
                                 costing_method="calculated")

        assert self._get("/api/v1/event-types").json()["event_types"] == []
        assert self._get("/api/v1/event-types/theirs").status_code == 404

    def test_every_write_writes_the_audit_action_it_declares(self):
        """The marker declares which actions a route MAY write; this is that
        the route actually wrote one, and which — the publication apart from
        the declaration, and each satellite under its own noun."""
        self._post("/api/v1/providers", {"key": "openai"})
        self._post("/api/v1/event-categories", {"key": "inference"})
        self._declare_calculated()
        self._put(
            "/api/v1/event-types/chat.completion/measurements/input_tokens",
            {"value_type": "integer", "unit": "token",
             "source_kind": "provider_response", "source_path": ["usage"]})
        self._post("/api/v1/event-types/chat.completion/publish")

        recorded = set(AuditRecord.objects.filter(
            tenant_id=self.tenant.id).values_list("action", flat=True))

        assert recorded == {"provider.declared", "event_category.declared",
                            "event_type.declared", "measurement.declared",
                            "event_type.published"}
