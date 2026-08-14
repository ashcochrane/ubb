"""The posting's cost reaches the published contract (#323).

#317 put four columns on the posting and #320 taught the compute spine to fill
them. Between them the three responses that publish a supplier cost already say
whether it is settled — but a caller reading `costing_status: "unresolved"` was
told a number was missing and nothing whatever about **what would settle it**,
which the registry's own summary calls a shrug rather than something a tenant
can act on. And the caller's own belief about the cost had no field at all, so
the only place to put it was the field that becomes COGS.

This module proves the two halves that close it, at the wire:

* `unresolved_reason` travels with the status on **every** response that carries
  it, naming the input that did not arrive;
* `claimed_provider_cost_micros` is published **beside** the supplier cost and
  is never mistaken for it — two fields, two meanings, on the same body.

**WHY A THIRD CLASS READS THE COMMITTED SPEC RATHER THAN THE SERIALISER.** The
reason is nullable — `NULL` on every settled posting, which is nearly all of
them — and the value set is `closed`, so the export writes a real `enum`. Those
two facts collide in a way no serialiser test can see: `enum` and `anyOf` at one
node are conjunctive, so an `enum` written **beside** a nullable union would
publish a document under which `null` is invalid, while the server goes on
returning `null` a few thousand times an hour. Every test in the first two
classes would stay green through that, because the wire body would be unchanged
— it is the DOCUMENT that would be lying. `EventTypeUpdateIn.costing_method` is
the precedent that gets it right, and the third class holds this field to the
same shape in both directions.

The values are imported, never spelled: `core.vocabulary` is generated from
`domain-vocabulary/`, and a literal here would be a second copy of a set the
registry owns (ADR-0008 §3).
"""

import json
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from core.vocabulary import (COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED,
                             UNRESOLVED_REASON_COST_RATE_MISSING)

# The recording body comes from there rather than being built here, and it is
# the migration ledger that decided so: the request still carries a retired
# correlation key, and its entry caps how many files may contain that word.
# Nothing in this module names it. See `usage_payload`'s own docstring.
from api.v1.tests.test_metering_endpoints import usage_payload

#: The committed contract, at the git root — `ubb/openapi/v1.json`. The same
#: address `test_deprecation.py` reads it from.
SPEC_PATH = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"

#: Every response schema that publishes a posting's supplier cost. The ack, the
#: lean list row and the audit receipt.
#:
#: THE CLAIM OF THIS MODULE IS THAT THESE THREE MOVE TOGETHER, so the set is
#: named once and both halves read it: the contract class walks it directly,
#: and `_WireCase.each_response` pairs each name with the body that schema
#: serves. A fourth response publishing the amount without the two fields
#: beside it is the finding, and it is one this set has to be able to state in
#: one place for either half to notice.
RESPONSES_CARRYING_THE_COST = ("RecordUsageResponse", "UsageEventOut",
                               "UsageEventDetailOut")


class _WireCase(TestCase):
    """A tenant with metering on, and the two calls that read a posting back."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Cost Contract",
                                            products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="cost_contract")

    def record(self, correlation, **body):
        payload = usage_payload(self.customer, correlation, **body)
        response = self.http.post(
            "/api/v1/metering/usage", data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def list_row(self, event_id):
        response = self.http.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        rows = [row for row in response.json()["data"] if row["id"] == event_id]
        self.assertEqual(len(rows), 1, "the posting is not on its own list")
        return rows[0]

    def detail(self, event_id):
        response = self.http.get(
            f"/api/v1/metering/usage/{event_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def each_response(self, ack):
        """`(schema name, body)` for all three responses that carry the cost.

        Built off `RESPONSES_CARRYING_THE_COST` rather than re-listing the
        names, so the module has ONE statement of which responses are in scope
        and the contract class and the wire classes cannot drift apart about
        it. The ack is passed in because it is the only one already in hand —
        the other two are fetched from the id it returns.
        """
        event_id = ack["event_id"]
        bodies = (ack, self.list_row(event_id), self.detail(event_id))
        return tuple(zip(RESPONSES_CARRYING_THE_COST, bodies))


class TheUnresolvedReasonTravelsWithTheStatusTest(_WireCase):
    """A status that says a cost is missing also says what would settle it."""

    def test_an_unresolved_posting_names_the_missing_input_on_all_three(self):
        """The ack, the list row and the receipt all carry the reason.

        A quantity nobody declared a Cost Rate for is the one unresolved cause
        reachable from the wire today, and the spine records it as such. The
        assertion is on the VALUE rather than on the key being present: a
        response carrying `unresolved_reason: null` beside `"unresolved"` would
        satisfy a presence check and tell a reader exactly as little as the
        status did on its own.
        """
        ack = self.record("unresolved",
                          measurements={"undeclared_quantity": 100})

        for name, body in self.each_response(ack):
            with self.subTest(response=name):
                self.assertEqual(body["costing_status"],
                                 COSTING_STATUS_UNRESOLVED)
                self.assertEqual(body["unresolved_reason"],
                                 UNRESOLVED_REASON_COST_RATE_MISSING)

    def test_a_settled_posting_publishes_no_reason_on_all_three(self):
        """The other direction, and it is what stops the field being noise.

        A quantity a Cost Rate DOES match settles the posting, so there is no
        missing input to name and the field is `null`. Without this the class
        above would pass against a serialiser that hard-coded one reason on to
        every posting it ever saw.

        SETTLED THROUGH THE RATE RATHER THAN THROUGH A CALLER-SUPPLIED FIGURE,
        AND #324 IS WHY. Sending the supplier cost on the request is the
        shorter route to `known` and was how this read first — but #324 makes
        that a **422** wherever the Event Type does not declare the reported
        method and the caller-supplied source kind, which no fixture here does.
        The test would have gone red inside somebody else's ticket, for a
        reason having nothing to do with what it asserts. Costing the quantity
        exercises the calculated path instead, which #324 does not touch.
        """
        # The rate's shape is left to the model's own defaults rather than
        # spelled out. That reads as brevity and is not: the word for it is
        # retired, slice 7 owns re-spelling it, and its ledger entry caps the
        # files that may still contain it at 21 — naming it here would have
        # made this the 22nd and failed the sweep, exactly as the correlation
        # key would have. The default IS the per-unit shape this needs.
        cost_rate_in_default_book(self.tenant, measurement_key="tokens",
                                  rate_per_unit_micros=42, unit_quantity=1)
        ack = self.record("known", measurements={"tokens": 100})

        for name, body in self.each_response(ack):
            with self.subTest(response=name):
                self.assertEqual(body["costing_status"], COSTING_STATUS_KNOWN)
                self.assertIn("unresolved_reason", body,
                              "the field is published on every response that "
                              "carries the status, present and null rather "
                              "than absent")
                self.assertIsNone(body["unresolved_reason"])

    def test_the_reason_is_read_off_the_row_rather_than_recomputed(self):
        """What each response publishes is what the table holds.

        Three serialisers could each reach their own conclusion and this suite
        would not notice, because all three would be reaching the same one
        today. Comparing every published answer to the COLUMN is what makes a
        fourth reader — or a replay path that re-derives instead of reading —
        fail here rather than in a tenant's reconciliation.
        """
        ack = self.record("row", measurements={"undeclared_quantity": 7})
        stored = Posting.objects.get(id=ack["event_id"])

        self.assertIsNotNone(stored.unresolved_reason,
                             "the fixture stopped producing an unresolved "
                             "posting, so the comparison below is vacuous")
        for name, body in self.each_response(ack):
            with self.subTest(response=name):
                self.assertEqual(body["unresolved_reason"],
                                 stored.unresolved_reason)


class TheClaimedFigureIsPublishedApartFromCOGSTest(_WireCase):
    """What the caller believes a call cost, published as its own field."""

    #: Two numbers that cannot be confused for each other in a failure message,
    #: and neither of which is a plausible default.
    CLAIMED = 987_654
    SUPPLIER = 4_200

    def _posting_with_a_claim(self, **overrides):
        """A posting carrying a claim, written at INSERT.

        The column is declared FROZEN and #318's trigger enforces it, so a
        claim can only ever be set as the row is created — which is what #324
        will do from the request. Until that lands nothing on the wire can
        produce one, and a test that recorded through the endpoint would prove
        only that both fields are null.
        """
        fields = {"provider_cost_micros": None, "billed_cost_micros": 0,
                  "costing_status": COSTING_STATUS_UNRESOLVED,
                  "unresolved_reason": UNRESOLVED_REASON_COST_RATE_MISSING}
        fields.update(overrides)
        return Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="claim",
            claimed_provider_cost_micros=self.CLAIMED, **fields)

    def test_the_claim_is_published_on_every_response_carrying_the_cost(self):
        """Both figures on one body, each under its own name.

        The ack is checked through the recording call rather than this fixture,
        because nothing can attach a claim to a recording request yet: what it
        proves there is that the FIELD is published, which is what a client
        generated against this contract needs before #324 gives it a value.
        """
        posting = self._posting_with_a_claim()

        for name, body in (
                ("UsageEventOut", self.list_row(str(posting.id))),
                ("UsageEventDetailOut", self.detail(str(posting.id)))):
            with self.subTest(response=name):
                self.assertEqual(body["claimed_provider_cost_micros"],
                                 self.CLAIMED)
                self.assertIsNone(
                    body["provider_cost_micros"],
                    "a claim settled the supplier cost — the two fields have "
                    "run together, which is the whole failure this ticket is "
                    "about")

        ack = self.record("ack-claim")
        self.assertIn("claimed_provider_cost_micros", ack)
        self.assertIsNone(ack["claimed_provider_cost_micros"])

    def test_a_claim_beside_a_real_supplier_cost_stays_the_other_number(self):
        """The case a single shared field would have destroyed.

        A posting whose supplier cost IS known and whose caller also stated a
        belief publishes both, and they differ. A serialiser that filled either
        field from the other would pass every assertion above and fail here.
        """
        posting = self._posting_with_a_claim(
            provider_cost_micros=self.SUPPLIER,
            costing_status=COSTING_STATUS_KNOWN, unresolved_reason=None)

        detail = self.detail(str(posting.id))
        self.assertEqual(detail["provider_cost_micros"], self.SUPPLIER)
        self.assertEqual(detail["claimed_provider_cost_micros"], self.CLAIMED)


def _admits_null(node):
    """Would a `null` instance validate against this schema node?

    Narrow on purpose — it answers for the shapes django-ninja renders for a
    vocabulary field and nothing else, which is the whole population the caller
    below walks. Two rules, both from JSON Schema's own conjunctive reading of
    keywords at one level:

    * a `null` member somewhere in the union is what admits `null` at all;
    * an `enum` or `const` BESIDE that union takes it away again, because every
      keyword at a node must hold and a list of three strings does not contain
      `null`.

    The second rule is the entire reason this function exists rather than a
    check for `{"type": "null"}` — a node can carry the null member and still
    refuse `null`, and that is precisely the document a marker in the wrong
    place would produce.
    """
    if any(key in node for key in ("enum", "const")):
        return False
    for key in ("anyOf", "oneOf"):
        members = node.get(key)
        if isinstance(members, list) and any(
                isinstance(member, dict) and member.get("type") == "null"
                for member in members):
            return True
    return node.get("type") == "null"


class TheAbsentReasonIsLegalOnThePublishedContractTest(SimpleTestCase):
    """The document says what the server does — for the nullable half too."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schemas = json.loads(
            SPEC_PATH.read_text(encoding="utf-8"))["components"]["schemas"]

    def test_the_reason_admits_null_on_every_response_that_carries_it(self):
        """`null` is the answer on nearly every posting, so it must be legal.

        If the generated `enum` landed beside the nullable union rather than
        inside its string branch, this is the only thing in the repository that
        would fail: the wire body would be unchanged, the export would be
        clean, and the contract would be refusing the response the server
        returns for every settled posting.
        """
        for name in RESPONSES_CARRYING_THE_COST:
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"]["unresolved_reason"]
                self.assertTrue(
                    _admits_null(node),
                    f"{name}.unresolved_reason refuses the `null` the server "
                    f"returns for every settled posting: {json.dumps(node)}")

    def test_the_reason_still_carries_the_registrys_three_values(self):
        """Admitting `null` must not have cost the enum.

        The cheap way to make the test above pass is to stop the concept being
        advertised at all, which would leave the field an unconstrained string
        and take the value set off the contract. Both halves are asserted, so
        neither can be bought with the other.
        """
        from core.vocabulary import UNRESOLVED_REASON_VALUES

        for name in RESPONSES_CARRYING_THE_COST:
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"]["unresolved_reason"]
                enums = [member["enum"] for member in node.get("anyOf", [])
                         if isinstance(member, dict) and "enum" in member]
                self.assertEqual(len(enums), 1,
                                 f"{name}.unresolved_reason should enumerate "
                                 f"the set once, in the string branch")
                self.assertEqual(sorted(enums[0]),
                                 sorted(UNRESOLVED_REASON_VALUES))

    def test_the_status_beside_it_does_not_admit_null(self):
        """The negative control, and it is what gives the check its edge.

        `costing_status` is required and non-nullable — every posting has an
        answer — so it renders a bare `enum` on a `type: string`. Running the
        same predicate over it proves the predicate discriminates rather than
        returning `True` for any node with a marker on it.
        """
        for name in RESPONSES_CARRYING_THE_COST:
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"]["costing_status"]
                self.assertFalse(_admits_null(node))

    def test_the_supplier_cost_admits_the_absent_case_on_all_three(self):
        """AC 1, which arrived at this ticket already paid — now pinned.

        Only ONE of the three was ever widened, and by #320 rather than here.
        The ack and the list row have been `Optional` since before slice 3 —
        but decoratively, because the column behind them was non-nullable with
        a default of zero, so nothing could put a `null` through them. The
        absent case became expressible in #317 (the column) and reachable in
        #320 (the spine that leaves it unset).

        So AC 1 is satisfied by three commits acting on two different layers,
        none of them this one, which is exactly the kind of claim nobody
        re-checks. It is asserted here rather than asserted in a commit
        message: `null` and `0` are both legal and are different JSON values,
        which is what "tell *not known* from *nothing* without inspecting
        another field" means once written down.

        THE AGGREGATE ROWS ARE NOT IN THIS SET, AND THAT IS #327's LINE RATHER
        THAN AN OVERSIGHT. Seven schemas publish a field of the same name that
        is a SUM over postings — a total is not a supplier cost, and what a
        total owes is its own completeness beside it, which is a pair this
        ticket does not build.
        """
        for name in RESPONSES_CARRYING_THE_COST:
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"]["provider_cost_micros"]
                self.assertTrue(
                    _admits_null(node),
                    f"{name}.provider_cost_micros cannot say `not known`")
                self.assertTrue(
                    any(member.get("type") == "integer"
                        for member in node.get("anyOf", [])),
                    f"{name}.provider_cost_micros admits null and nothing "
                    f"else — zero has stopped being expressible")

    def test_the_claimed_figure_states_its_meaning_on_the_wire(self):
        """The meaning is in the DOCUMENT, not in a Python comment beside it.

        "Never COGS" is the whole point of the field having its own name, and a
        generated client's user never reads `api/v1/schemas.py`. A `#` comment
        would satisfy a reviewer skimming the diff and reach nobody.
        """
        for name in RESPONSES_CARRYING_THE_COST:
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"][
                    "claimed_provider_cost_micros"]
                description = node.get("description", "")
                self.assertIn("never COGS", description,
                              f"{name}.claimed_provider_cost_micros publishes "
                              f"no description saying what it is not")
