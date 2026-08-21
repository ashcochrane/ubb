"""Ruling 15: the six-of-ten gap was FUNCTIONAL, and it closes here (#366).

A rule can be pinned on ten grouping slots. The published contract named six —
#276 widened the columns and its acceptance criteria forbade it to rename a
published property, so six names sat over six of ten columns and the other four
had no property at all.

**THAT WAS NOT A SPELLING PROBLEM.** An unpinned selector is stored as the empty
string, and a reprice body that cannot NAME slot seven sends the empty string
for it — which is exactly what matches a rule leaving slot seven unpinned. So a
rule pinned on slot seven could be written server-side, was returned by the read
route, and **could be matched by no publish body in existence**: the price it
charged was frozen for as long as it lived. There was no error, no 404 and no
warning; a publish naming everything else about it simply said *no active rate*.

This module is the functional half of ruling 15, and it is not proved by the
schema assertion beside it in
`api/v1/tests/test_grouping_values_on_the_contract.py`. That one asks whether
the property is PUBLISHED. This one asks whether the rule is REACHABLE, which is
a different question with a different failure: a body could carry all ten
properties and still be translated wrongly on the way to `Rate.SELECTORS`, and
every document-shaped check would stay green while the wrong rule was repriced.

**THE SEVENTH SLOT, DELIBERATELY.** Not the tenth and not the first: seven is
the first slot that had no published property, so a test written against it
fails on the old contract at the schema (the key is dropped) and on any
half-conversion at the match (the rule is not found). One-through-six would pass
before this commit.

⚠ **THE BOOK IS BUILT THROUGH `_helpers.cost_book` RATHER THAN OVER HTTP**, and
that is a vocabulary constraint rather than a shortcut. A book-create body names
the discriminator between a cost book and a price one, which is a retired word
slice 4 owns and whose ledger count is a ceiling on spread as much as a floor —
a new module spelling it would put the count over its entry and fail the sweep.
The helper already carries it for its callers. Everything this module is ABOUT
goes over the real HTTP surface.
"""
import json

from django.test import Client, TestCase

from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import cost_book
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey

#: The slot the old contract could not name. `Rate.SELECTORS` carries all ten;
#: the published bodies carried the first six.
UNREACHABLE_SLOT = "grouping_field_7"

#: A slot the old contract COULD name, kept beside it as the discriminating
#: control: a conversion that published four new properties and wired them to
#: the wrong columns would still pass every case about slot seven alone.
REACHABLE_SLOT = "grouping_field_2"

QUANTITY = "input_tokens"

#: The tenant's own key for each slot this module pins, because the act that
#: OPENS a rule addresses a slot by the key the tenant declared rather than by
#: the column (#367 — the body that named the column directly left with its
#: route). The reprice under test still names columns, which is why the cases
#: below are written in columns and only this map is in keys.
DECLARED_KEY_OF = {UNREACHABLE_SLOT: "tier", REACHABLE_SLOT: "segment"}


class ARulePinnedOnAnySlotIsReachableTest(TestCase):
    """Written on the seventh slot, then repriced through the API, end to end."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Slots", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        declares_a_quantity(self.tenant, QUANTITY)
        for slot, key in DECLARED_KEY_OF.items():
            DimensionService.declare(self.tenant, key=key, slot=slot,
                                     scope="tenant")
        self.book = cost_book(self.tenant, key="openai", provider="openai")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http.post(path, data=json.dumps(body or {}),
                              content_type="application/json", **self._auth())

    def _add(self, **pins):
        """Open a rule, through the only surface that still does it (#367).

        The immediate add-a-rule route is gone — adding a rule is a declared
        change on a publish — so this declares one and publishes it in the same
        breath. The rule that lands is the same rule: this module's subject is
        which SLOTS a rule can be pinned on and repriced by, and that is
        unchanged by which act opened it.

        ⚠ **THE TWO BODIES NAME A SLOT DIFFERENTLY, AND THAT IS THE POINT OF
        HAVING BOTH.** A declared change carries the tenant's own grouping KEY,
        which survives the key being rebound to another slot; the immediate
        reprice body names the COLUMN. So a caller here passes the column and
        this translates, which keeps every case below written in the one
        vocabulary the reprice under test speaks.
        """
        pinned = {key: value for key, value in pins.items()
                  if key.startswith("grouping_field_")}
        terms = {key: value for key, value in pins.items() if key not in pinned}
        change = {"kind": "add", "measurement_key": QUANTITY,
                  "provider": "openai", "rate_per_unit_micros": 5_000,
                  "unit_quantity": 1_000_000, **terms}
        if pinned:
            change["grouping_fields"] = {DECLARED_KEY_OF[slot]: value
                                         for slot, value in pinned.items()}
        declared = self._post(
            f"/api/v1/metering/pricing/books/{self.book.id}/publishes",
            {"changes": [change]})
        if declared.status_code != 200:
            return declared
        return self._post(
            f"/api/v1/metering/pricing/books/{self.book.id}"
            f"/publishes/{declared.json()['id']}/publish")

    def _reprice(self, *, to, **pins):
        """Reprice the rule pinned on these slots, and publish the change.

        ⚠ **IT NAMES THE SLOT BY THE TENANT'S DECLARED KEY NOW (#368).** The
        immediate reprice route took a body naming the physical COLUMN; it is
        deleted with the last of the retired audit action names it wrote, so a
        reprice is a declared change like any other and speaks the one
        vocabulary a change body has. Ruling 15's gap stays closed either way:
        what it asked for is that a rule pinned on any of the ten slots be
        reachable, and the registry resolves whichever slot a declared key is
        bound to.
        """
        change = {"kind": "reprice", "measurement_key": QUANTITY,
                  "provider": "openai", "rate_per_unit_micros": to}
        if pins:
            change["grouping_fields"] = {DECLARED_KEY_OF[slot]: value
                                         for slot, value in pins.items()}
        declared = self._post(
            f"/api/v1/metering/pricing/books/{self.book.id}/publishes",
            {"changes": [change]})
        if declared.status_code != 200:
            return declared
        return self._post(
            f"/api/v1/metering/pricing/books/{self.book.id}"
            f"/publishes/{declared.json()['id']}/publish")

    def _rules(self):
        """Every version of every rule in the book, newest first."""
        response = self.http.get(
            f"/api/v1/metering/pricing/books/{self.book.id}/rates"
            f"?include_history=true", **self._auth())
        assert response.status_code == 200, response.content
        return response.json()["data"]

    def test_a_rule_can_be_written_on_the_slot_the_contract_could_not_name(self):
        """Half one: the property reaches the column.

        A body key no schema publishes is DROPPED by django-ninja rather than
        refused, so before #366 this same request answered 200 with the slot
        left empty — the rule was created, on the wrong shape, silently. That is
        why this asserts the stored column rather than the status code.

        ⚠ The act that opens a rule is a publish since #367, so what is read
        back is the rule the publish opened rather than a create's echo of its
        own request — which is the stronger of the two reads anyway: an echo can
        agree with a body that never reached a column.
        """
        response = self._add(**{UNREACHABLE_SLOT: "batch"})

        self.assertEqual(response.status_code, 200, response.content)
        (opened,) = response.json()["opened_rule_ids"]
        self.assertEqual(
            getattr(Rate.objects.get(id=opened), UNREACHABLE_SLOT), "batch")
        (row,) = self._rules()
        self.assertEqual(row[UNREACHABLE_SLOT], "batch")

    def test_a_rule_on_that_slot_reprices_through_the_publish_act(self):
        """Half two, and the half the schema assertion cannot make.

        The publish matches on `Rate.SELECTORS`, which are column names. This is
        what proves the body reaches them: a new version at the new price, under
        the SAME lineage, still pinned on the same slot — a reprice that matched
        nothing would answer 422 and a reprice that matched a different rule
        would leave this one at its old price.
        """
        self.assertEqual(self._add(**{UNREACHABLE_SLOT: "batch"}).status_code, 200)
        opening = self._rules()
        self.assertEqual(len(opening), 1)

        published = self._reprice(to=9_000, **{UNREACHABLE_SLOT: "batch"})

        self.assertEqual(published.status_code, 200, published.content)
        versions = self._rules()
        self.assertEqual(len(versions), 2)
        newest, superseded = versions
        self.assertEqual(newest["rate_per_unit_micros"], 9_000)
        self.assertEqual(superseded["rate_per_unit_micros"], 5_000)
        self.assertEqual(newest["lineage_id"], opening[0]["lineage_id"])
        self.assertEqual(newest[UNREACHABLE_SLOT], "batch")
        self.assertIsNone(newest["valid_to"])
        self.assertIsNotNone(superseded["valid_to"])

    def test_an_empty_slot_in_the_body_still_means_a_rule_that_pins_nothing(self):
        """THE PROPERTY THAT MUST SURVIVE THE WIDENING, in both directions.

        The four new properties do not change what an empty selector means: it
        addresses the rule that leaves that slot UNPINNED, exactly as the six
        older ones always did. If the widening had made an omitted slot a
        wildcard instead, a publish meaning to move the general rule would have
        moved whichever pinned one it happened to find — and the tenant would
        see a price change on a customer segment they never named.

        Both rules exist at once here, which is what makes this discriminate.
        With only one in the book a wildcard reading and an exact-match reading
        give the same answer.
        """
        self.assertEqual(self._add(**{UNREACHABLE_SLOT: "batch"}).status_code, 200)
        self.assertEqual(self._add().status_code, 200)

        published = self._reprice(to=9_000)

        self.assertEqual(published.status_code, 200, published.content)
        by_slot = {rule[UNREACHABLE_SLOT]: rule for rule in self._rules()
                   if rule["valid_to"] is None}
        self.assertEqual(by_slot[""]["rate_per_unit_micros"], 9_000,
                         "the unpinned rule is the one an empty body addresses")
        self.assertEqual(by_slot["batch"]["rate_per_unit_micros"], 5_000,
                         "the pinned rule is untouched by a body that did not "
                         "name its slot")

    def test_a_body_naming_a_slot_no_rule_pins_reprices_nothing(self):
        """The other direction of the same property, said as a refusal.

        A publish that names slot seven when the only rule leaves it unpinned
        must NOT fall back to that rule. It answers 422 and the book is where it
        was — all-or-nothing, so nothing partial is written either.
        """
        self.assertEqual(self._add().status_code, 200)
        before = self._rules()

        published = self._reprice(to=9_000, **{UNREACHABLE_SLOT: "batch"})

        self.assertEqual(published.status_code, 422, published.content)
        self.assertEqual(self._rules(), before)

    def test_the_four_new_slots_are_wired_to_their_own_columns(self):
        """A widening can publish ten properties and cross two of them.

        Nothing above would notice: every case so far uses ONE slot, so a body
        key wired to the neighbouring column would write the value, find it
        again on the same wrong column, and reprice correctly throughout. Two
        rules differing only in WHICH slot carries the same value is what
        separates them.
        """
        self.assertEqual(self._add(**{UNREACHABLE_SLOT: "batch"}).status_code, 200)
        self.assertEqual(self._add(**{REACHABLE_SLOT: "batch"}).status_code, 200)

        published = self._reprice(to=9_000, **{UNREACHABLE_SLOT: "batch"})

        self.assertEqual(published.status_code, 200, published.content)
        open_rules = [rule for rule in self._rules() if rule["valid_to"] is None]
        moved = [rule for rule in open_rules
                 if rule["rate_per_unit_micros"] == 9_000]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0][UNREACHABLE_SLOT], "batch")
        self.assertEqual(moved[0][REACHABLE_SLOT], "")
