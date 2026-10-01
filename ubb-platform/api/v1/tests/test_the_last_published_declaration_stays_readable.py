"""A revised Event Type still answers what it said when last published (#573).

A tenant who revises a declaration after publishing it has two declarations in
play: the one their deployed integration was generated against, and the one
they are editing. Until this ticket the row held only the second — a child edit
returned the Event Type to draft IN PLACE, and the content publication had
pinned was gone with it. Only the revision number and its date survived, which
count publications without saying what any of them contained.

**Everything here goes through the tenant's own routes** — declare, publish,
revise by editing a part, publish again — and asks the kernel read what the
last publication said. Nothing writes a row directly: the claim is about what
the lifecycle a tenant actually drives leaves behind.

**The control is the comparator itself.** `_as_served` turns the route's own
answer — the LIVE declaration — into the read's shape. At the moment of
publication the two agree, which is what proves the comparison can pass; after
a revision they must not, which is what proves a read answering with the draft
would fail every test below that asserts the read is unmoved.

The read is internal. That it adds nothing to the published contract is held
by the export showing no diff, and stated once more at the bottom of this
module from the other side: the route's body does not grow a field.
"""
import json
from datetime import datetime

import pytest
from django.test import Client

from apps.platform.event_types.publication import (
    PublishedDeclaration, PublishedMeasurement, PublishedReportedCostMapping,
    last_published_declaration,
)
from apps.platform.tenants.models import Tenant, TenantApiKey

KEY = "chat.completion"
ROUTE = f"/api/v1/event-types/{KEY}"

INPUT_TOKENS = {"display_name": "Input tokens", "value_type": "integer",
                "unit": "token", "required_for_costing": True,
                "source_kind": "provider_response",
                "source_path": ["usage", "input_tokens"]}
OUTPUT_TOKENS = {"display_name": "Output tokens", "value_type": "integer",
                 "unit": "token", "required_for_costing": False,
                 "source_kind": "provider_response",
                 "source_path": ["usage", "output_tokens"]}
MAPPING = {"source_kind": "provider_response",
           "amount_representation": "major_units_decimal",
           "source_path": ["usage", "total_cost"], "currency_path": [],
           "currency": "usd"}


def _as_served(body):
    """The route's answer about the LIVE declaration, in the read's shape.

    What a read that fell back to the current rows would return. Built from
    the published contract's own body so the control cannot share a mistake
    with the read it is the control for.
    """
    mapping = body["reported_cost_mapping"]
    return PublishedDeclaration(
        key=body["key"],
        costing_method=body["costing_method"],
        source_shape_id=body["source_shape_id"],
        source_shape_label=body["source_shape_label"],
        published_revision=body["published_revision"],
        published_at=datetime.fromisoformat(body["published_at"]),
        measurements=tuple(
            PublishedMeasurement(
                code=m["code"], value_type=m["value_type"], unit=m["unit"],
                required_for_costing=m["required_for_costing"],
                source_kind=m["source_kind"],
                source_path=tuple(m["source_path"]))
            for m in sorted(body["measurements"], key=lambda m: m["code"])),
        reported_cost_mapping=(None if mapping is None else
                               PublishedReportedCostMapping(
            source_kind=mapping["source_kind"],
            source_path=tuple(mapping["source_path"]),
            amount_representation=mapping["amount_representation"],
            currency=mapping["currency"],
            currency_path=tuple(mapping["currency_path"]))),
    )


@pytest.mark.django_db
class TestTheLastPublishedDeclarationStaysReadable:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    # -- the tenant's own routes ------------------------------------------

    def _call(self, method, path, data=None):
        auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}
        if method == "get":
            response = self.client.get(path, **auth)
        else:
            response = getattr(self.client, method)(
                path, data=json.dumps(data or {}),
                content_type="application/json", **auth)
        assert response.status_code < 300, response.content
        return response.json() if response.content else None

    def _declare(self):
        self._call("post", "/api/v1/event-types",
                   {"key": KEY, "costing_method": "reported",
                    "source_shape_id": "openai.responses.python.v1"})
        self._call("put", f"{ROUTE}/measurements/input_tokens", INPUT_TOKENS)
        self._call("put", f"{ROUTE}/measurements/output_tokens", OUTPUT_TOKENS)
        self._call("put", f"{ROUTE}/reported-cost-mapping", MAPPING)

    def _publish(self):
        return self._call("post", f"{ROUTE}/publish")

    def _live(self):
        return self._call("get", ROUTE)

    def _read(self):
        return last_published_declaration(tenant=self.tenant, key=KEY)

    def _declared_and_published(self):
        self._declare()
        return self._publish()

    # -- publication records what it pinned --------------------------------

    def test_publishing_records_the_declaration_it_pinned(self):
        """Every pinned element, of the Event Type and of each part beneath
        it — stated as literals here, once, so the shape is asserted against
        something other than the route that produced it."""
        body = self._declared_and_published()

        published = self._read()

        assert published == PublishedDeclaration(
            key=KEY,
            costing_method="reported",
            source_shape_id="openai.responses.python.v1",
            source_shape_label="",
            published_revision=1,
            published_at=datetime.fromisoformat(body["published_at"]),
            measurements=(
                PublishedMeasurement(
                    code="input_tokens", value_type="integer", unit="token",
                    required_for_costing=True,
                    source_kind="provider_response",
                    source_path=("usage", "input_tokens")),
                PublishedMeasurement(
                    code="output_tokens", value_type="integer", unit="token",
                    required_for_costing=False,
                    source_kind="provider_response",
                    source_path=("usage", "output_tokens")),
            ),
            reported_cost_mapping=PublishedReportedCostMapping(
                source_kind="provider_response",
                source_path=("usage", "total_cost"),
                amount_representation="major_units_decimal",
                currency="usd", currency_path=()),
        )
        # The comparator the controls below rely on CAN agree: at the moment
        # of publication the live declaration is the published one.
        assert _as_served(body) == published

    # -- a revision leaves it where it was ---------------------------------

    @pytest.mark.parametrize("revise", [
        pytest.param(
            lambda t: t._call(
                "put", f"{ROUTE}/measurements/input_tokens",
                {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]}),
            id="a measurement's structured path is changed"),
        pytest.param(
            lambda t: t._call(
                "put", f"{ROUTE}/measurements/cached_tokens",
                {**INPUT_TOKENS, "required_for_costing": False,
                 "source_path": ["usage", "cached_tokens"]}),
            id="a measurement is added"),
        pytest.param(
            lambda t: t._call("delete",
                              f"{ROUTE}/measurements/output_tokens"),
            id="a measurement is withdrawn"),
        pytest.param(
            lambda t: t._call(
                "put", f"{ROUTE}/reported-cost-mapping",
                {**MAPPING, "amount_representation": "micros",
                 "source_path": ["usage", "cost_micros"]}),
            id="the reported-cost mapping is changed"),
        pytest.param(
            lambda t: t._call("delete", f"{ROUTE}/reported-cost-mapping"),
            id="the reported-cost mapping is withdrawn"),
        pytest.param(
            lambda t: t._call("patch", ROUTE,
                              {"source_shape_id": "google.genai.python.v1"}),
            id="the response shape is changed"),
        pytest.param(
            lambda t: t._call("patch", ROUTE,
                              {"costing_method": "calculated"}),
            id="the costing method is changed"),
    ])
    def test_a_revision_does_not_move_what_was_last_published(self, revise):
        body = self._declared_and_published()
        before = self._read()

        revise(self)

        draft = self._live()
        assert draft["declaration_status"] == "draft"
        # Only the count and the date survive on the row a tenant reads, and
        # both still say the first publication.
        assert draft["published_revision"] == 1
        assert draft["published_at"] == body["published_at"]

        after = self._read()
        assert after == before
        assert after.published_revision == 1
        assert after.published_at == datetime.fromisoformat(
            body["published_at"])
        # THE CONTROL. The same comparator that agreed at publication now
        # disagrees: the live declaration really did change, so a read that
        # answered with it could not have passed the equality above.
        assert _as_served(draft) != after

    def test_several_revisions_in_a_row_still_leave_it_where_it_was(self):
        """The draft may drift as far as the tenant likes. One edit and five
        are the same case to the read, and the second edit is the one a
        copy taken lazily — at the first revision — would still pass."""
        self._declared_and_published()
        before = self._read()

        self._call("put", f"{ROUTE}/measurements/input_tokens",
                   {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]})
        self._call("put", f"{ROUTE}/measurements/input_tokens",
                   {**INPUT_TOKENS, "unit": "character",
                    "source_path": ["usage", "prompt_characters"]})
        self._call("delete", f"{ROUTE}/reported-cost-mapping")
        self._call("patch", ROUTE, {"costing_method": "calculated"})

        assert self._read() == before
        assert _as_served(self._live()) != before

    # -- never published ----------------------------------------------------

    def test_a_declaration_never_published_has_no_last_published_one(self):
        """It has content — a costing method, two quantities and a mapping —
        and the read still answers that nothing was published. The draft is
        never the fallback."""
        self._declare()

        assert self._live()["published_revision"] == 0
        assert self._read() is None

    def test_a_key_nobody_declared_has_none_either(self):
        assert last_published_declaration(tenant=self.tenant,
                                          key="never.declared") is None

    def test_a_refused_publication_records_nothing(self):
        """A `reported` declaration with no mapping is refused, and a refusal
        is not a publication: there is still nothing to read."""
        self._call("post", "/api/v1/event-types",
                   {"key": KEY, "costing_method": "reported"})
        refused = self.client.post(
            f"{ROUTE}/publish", data="{}", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        assert refused.status_code == 409
        assert self._read() is None

    # -- publishing again ---------------------------------------------------

    def test_publishing_an_unchanged_declaration_again_moves_nothing(self):
        first = self._declared_and_published()
        before = self._read()

        again = self._publish()

        assert again["published_revision"] == 1
        assert again["published_at"] == first["published_at"]
        assert self._read() == before

    def test_publishing_a_changed_declaration_replaces_what_is_read(self):
        """Exactly one revision on, and the read now says the new content —
        the old one is not what a reader asking for the current publication
        gets."""
        self._declared_and_published()
        before = self._read()
        self._call("put", f"{ROUTE}/measurements/input_tokens",
                   {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]})

        republished = self._publish()

        assert republished["published_revision"] == 2
        after = self._read()
        assert after == _as_served(republished)
        assert after.published_revision == before.published_revision + 1
        assert after.measurements[0].source_path == ("usage", "prompt_tokens")
        assert after != before

    def test_a_revision_after_the_second_publication_keeps_the_second(self):
        self._declared_and_published()
        self._call("put", f"{ROUTE}/measurements/input_tokens",
                   {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]})
        self._publish()
        second = self._read()

        self._call("delete", f"{ROUTE}/measurements/output_tokens")

        assert self._read() == second
        assert second.published_revision == 2

    # -- whose it is ----------------------------------------------------------

    def test_another_tenants_declaration_of_the_same_key_is_not_read(self):
        self._declared_and_published()
        other = Tenant.objects.create(name="Other", products=["metering"])

        assert last_published_declaration(tenant=other, key=KEY) is None

    # -- and it stays internal ----------------------------------------------

    def test_the_route_serves_no_more_than_it_did(self):
        """The read is the kernel's, not the contract's. `openapi/v1.json`
        showing no diff is what holds the schema; this holds the body, which
        a serializer could grow without the schema noticing."""
        body = self._declared_and_published()

        assert sorted(body) == [
            "category_key", "costing_method", "declaration_status", "key",
            "measurements", "provider_key", "publication_blockers",
            "published_at", "published_revision", "reported_cost_mapping",
            "source_shape_id", "source_shape_label"]
