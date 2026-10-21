"""An agreed price is declared, repriced and retired through the publish act
(#553, spec stories 1-12 and 20).

A Pricing Book holds an agreed price for a top-level kind of work as a line of
its own, opened and closed by the same declare-then-publish act as a rate: the
same draft, the same diff, the same forward dating, and one publish may carry
both kinds of line. What is asked here is what only the route can answer — the
request a tenant sends, the diff it reads before committing, the publish
record's account of what it opened and closed, and the refusals, each by what
it names.

The line's database rule (its window is frozen and closed once) is held in
`apps/metering/pricing/tests/test_an_agreed_price_window_is_held_by_the_database.py`,
and what a start and a delivery do with a published price in
`test_an_agreed_price_is_charged_end_to_end.py`.
"""
import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import PricingBookPublish, Rate, TaskPrice
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant, TenantApiKey

#: A top-level kind sold at one agreed price, one sold per event, one declared
#: only as contained work, and one retired.
SOLD_WHOLE = "transcode"
SOLD_PER_EVENT = "chat"
CONTAINED_ONLY = "render_step"
RETIRED = "legacy_render"

PRICE = 8_000_000
NEW_PRICE = 9_500_000
QUANTITY = "input_tokens"


def _in_days(days):
    return timezone.now() + timedelta(days=days)


def an_agreed_price(kind, task_type=SOLD_WHOLE, **amount):
    """One agreed-price change as a tenant SENDS it."""
    return {"line": "agreed_price", "kind": kind, "task_type": task_type,
            **amount}


class _APricingBookMixin:

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T",
                                            products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        declares_a_quantity(self.tenant, QUANTITY)
        self._put("/api/v1/task-types", {"task_types": [
            {"key": SOLD_WHOLE, "pricing_mode": "fixed", "uncapped": True},
            {"key": SOLD_PER_EVENT, "uncapped": True},
            {"key": CONTAINED_ONLY, "kind": "subtask", "uncapped": True},
            {"key": RETIRED, "pricing_mode": "fixed", "uncapped": True},
        ]})
        self._put("/api/v1/task-types", {"task_types": [
            {"key": RETIRED, "pricing_mode": "fixed", "uncapped": True,
             "retired": True}]})
        self.book = self._ok("post", "/api/v1/metering/pricing/pricing-books",
                             {"key": "catalogue", "name": "Catalogue",
                              "is_default": True})
        self.publishes = (f"/api/v1/metering/pricing/books/"
                          f"{self.book['id']}/publishes")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _send(self, method, path, body=None):
        if method == "get":
            return self.http.get(path, **self._auth())
        return getattr(self.http, method)(
            path, data=json.dumps(body or {}),
            content_type="application/json", **self._auth())

    def _ok(self, method, path, body=None):
        response = self._send(method, path, body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _put(self, path, body):
        return self._ok("put", path, body)

    def declare(self, *changes, effective_at=None):
        body = {"changes": list(changes)}
        if effective_at is not None:
            body["effective_at"] = effective_at.isoformat()
        return self._send("post", self.publishes, body)

    def publish(self, *changes, effective_at=None):
        declared = self.declare(*changes, effective_at=effective_at)
        self.assertEqual(declared.status_code, 200, declared.content)
        return self._ok("post",
                        f"{self.publishes}/{declared.json()['id']}/publish")

    def refused(self, *changes, effective_at=None):
        """A declaration refused before anything is written — no draft is
        recorded — and the problem it answered with."""
        drafts = PricingBookPublish.objects.filter(tenant=self.tenant).count()
        response = self.declare(*changes, effective_at=effective_at)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            PricingBookPublish.objects.filter(tenant=self.tenant).count(),
            drafts)
        return response.json()


class AnAgreedPriceIsAddedRepricedAndRetiredTest(_APricingBookMixin, TestCase):

    def test_a_draft_shows_the_agreed_price_it_will_add(self):
        response = self.declare(an_agreed_price(
            "add", agreed_price_micros=PRICE))

        self.assertEqual(response.status_code, 200, response.content)
        (row,) = response.json()["diff"]
        self.assertEqual(row, {"line": "agreed_price", "kind": "add",
                               "task_type": SOLD_WHOLE, "before": None,
                               "after": {"agreed_price_micros": PRICE}})
        self.assertFalse(TaskPrice.objects.filter(tenant=self.tenant).exists())

    def test_publishing_opens_the_line_and_says_so(self):
        published = self.publish(an_agreed_price(
            "add", agreed_price_micros=PRICE))

        (opened,) = published["opened_agreed_price_ids"]
        self.assertEqual(published["closed_agreed_price_ids"], [])
        # `opened_rule_ids` keeps naming rates only.
        self.assertEqual(published["opened_rule_ids"], [])
        line = TaskPrice.objects.get(pk=opened)
        self.assertEqual(line.agreed_price_micros, PRICE)
        self.assertEqual(line.task_type, SOLD_WHOLE)
        self.assertEqual(line.book_version_from, 2)
        self.assertIsNone(line.book_version_to)
        self.assertIsNone(line.valid_to)

    def test_a_reprice_closes_the_line_and_opens_its_successor(self):
        added = self.publish(an_agreed_price("add",
                                             agreed_price_micros=PRICE))
        (first,) = added["opened_agreed_price_ids"]

        declared = self.declare(an_agreed_price(
            "reprice", agreed_price_micros=NEW_PRICE)).json()
        (row,) = declared["diff"]
        self.assertEqual(row["before"], {"agreed_price_micros": PRICE})
        self.assertEqual(row["after"], {"agreed_price_micros": NEW_PRICE})
        repriced = self._ok("post",
                            f"{self.publishes}/{declared['id']}/publish")

        self.assertEqual(repriced["closed_agreed_price_ids"], [first])
        (second,) = repriced["opened_agreed_price_ids"]
        old, new = (TaskPrice.objects.get(pk=first),
                    TaskPrice.objects.get(pk=second))
        # One instant closes the old line and opens the new one.
        self.assertEqual(old.valid_to, new.valid_from)
        self.assertEqual(old.book_version_to, 2)
        self.assertEqual(new.book_version_from, 3)
        # The successor continues the line's history.
        self.assertEqual(new.lineage_id, old.lineage_id)

    def test_a_retirement_closes_the_line_and_opens_none(self):
        (first,) = self.publish(an_agreed_price(
            "add", agreed_price_micros=PRICE))["opened_agreed_price_ids"]

        retired = self.publish(an_agreed_price("retire"))

        self.assertEqual(retired["closed_agreed_price_ids"], [first])
        self.assertEqual(retired["opened_agreed_price_ids"], [])
        self.assertIsNotNone(TaskPrice.objects.get(pk=first).valid_to)

    def test_zero_is_a_price(self):
        published = self.publish(an_agreed_price("add",
                                                 agreed_price_micros=0))

        (opened,) = published["opened_agreed_price_ids"]
        self.assertEqual(TaskPrice.objects.get(pk=opened).agreed_price_micros, 0)

    def test_a_kind_sold_per_event_may_be_priced_before_it_is_switched(self):
        """Story 9: the price is declared first, so no start is refused in the
        window between switching the kind to fixed pricing and pricing it."""
        published = self.publish(an_agreed_price(
            "add", SOLD_PER_EVENT, agreed_price_micros=PRICE))

        self.assertEqual(len(published["opened_agreed_price_ids"]), 1)


class APublishCarriesBothKindsOfLineAtOnceTest(_APricingBookMixin, TestCase):
    """Story 5: one publish carries rate changes and agreed-price changes, and
    applies them together or not at all."""

    RATE = {"line": "rate", "kind": "add", "measurement_key": QUANTITY,
            "rate_per_unit_micros": 3}

    def test_both_lines_open_in_one_publish(self):
        published = self.publish(self.RATE, an_agreed_price(
            "add", agreed_price_micros=PRICE))

        self.assertEqual(len(published["opened_rule_ids"]), 1)
        self.assertEqual(len(published["opened_agreed_price_ids"]), 1)

    def test_one_refused_line_writes_neither(self):
        body = self.refused(self.RATE, an_agreed_price(
            "add", CONTAINED_ONLY, agreed_price_micros=PRICE))

        self.assertIn("change 1", body["detail"])
        self.assertFalse(Rate.objects.filter(tenant=self.tenant).exists())


class WhatAPublishRefusesTest(_APricingBookMixin, TestCase):
    """Stories 7, 8, 10 and 12, each refused by what it names, before a draft
    is written."""

    def test_a_kind_declared_only_as_contained_work_is_refused(self):
        body = self.refused(an_agreed_price(
            "add", CONTAINED_ONLY, agreed_price_micros=PRICE))

        self.assertIn("declared only as contained work", body["detail"])

    def test_a_kind_nobody_declared_is_refused(self):
        body = self.refused(an_agreed_price(
            "add", "transcoed", agreed_price_micros=PRICE))

        self.assertIn("no kind of work is declared as 'transcoed'",
                      body["detail"])

    def test_a_retired_kind_is_refused(self):
        body = self.refused(an_agreed_price(
            "add", RETIRED, agreed_price_micros=PRICE))

        self.assertIn(f"'{RETIRED}' is retired", body["detail"])

    def test_a_second_line_in_force_for_one_kind_is_refused(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))

        body = self.refused(an_agreed_price("add",
                                            agreed_price_micros=NEW_PRICE))

        self.assertIn("already holds an agreed price for 'transcode'",
                      body["detail"])

    def test_a_line_scheduled_to_open_later_is_a_line_in_force_too(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE),
                     effective_at=_in_days(10))

        body = self.refused(an_agreed_price("add",
                                            agreed_price_micros=NEW_PRICE),
                            effective_at=_in_days(20))

        self.assertIn("already holds an agreed price", body["detail"])

    def test_two_changes_to_one_kind_in_one_publish_are_refused(self):
        body = self.refused(
            an_agreed_price("add", agreed_price_micros=PRICE),
            an_agreed_price("add", agreed_price_micros=NEW_PRICE))

        self.assertIn("already changes the agreed price for 'transcode'",
                      body["detail"])

    def test_a_negative_price_is_refused(self):
        response = self.declare(an_agreed_price(
            "add", agreed_price_micros=-1))

        self.assertEqual(response.status_code, 422, response.content)
        (error,) = response.json()["errors"]
        self.assertEqual(error["loc"][-1], "agreed_price_micros")
        self.assertEqual(error["type"], "greater_than_equal")

    def test_an_add_states_its_amount(self):
        body = self.refused(an_agreed_price("add"))

        self.assertIn("agreed_price_micros is required on add",
                      body["detail"])

    def test_a_retirement_states_no_amount(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))

        body = self.refused(an_agreed_price("retire",
                                            agreed_price_micros=PRICE))

        self.assertIn("states no agreed_price_micros", body["detail"])

    def test_a_reprice_of_a_kind_with_no_price_is_refused(self):
        body = self.refused(an_agreed_price("reprice",
                                            agreed_price_micros=PRICE))

        self.assertIn("nothing to reprice", body["detail"])

    def test_a_cost_book_holds_no_agreed_price(self):
        cost_book = self._ok("post", "/api/v1/metering/pricing/cost-books",
                             {"provider_key": "openai", "key": "openai",
                              "is_default": True})
        response = self._send(
            "post", f"/api/v1/metering/pricing/books/{cost_book['id']}"
                    f"/publishes",
            {"changes": [an_agreed_price("add", agreed_price_micros=PRICE)]})

        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("declare it in a Pricing Book",
                      response.json()["detail"])

    def test_a_line_whose_kind_was_retired_can_still_be_retired(self):
        """The refusals are about the line a change OPENS. A price left behind
        by a kind retired since is exactly the line a tenant must close."""
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        self._put("/api/v1/task-types", {"task_types": [
            {"key": SOLD_WHOLE, "pricing_mode": "fixed", "uncapped": True,
             "retired": True}]})

        retired = self.publish(an_agreed_price("retire"))

        self.assertEqual(len(retired["closed_agreed_price_ids"]), 1)


class TheBooksDiaryReadsAgreedPricesTest(_APricingBookMixin, TestCase):
    """The book's own boundary — ruling 14b's floor — counts an agreed price
    scheduled in it exactly as it counts a rate."""

    def test_a_change_dated_behind_a_scheduled_agreed_price_is_refused(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE),
                     effective_at=_in_days(10))

        response = self.declare(
            {"line": "rate", "kind": "add", "measurement_key": QUANTITY,
             "rate_per_unit_micros": 3},
            effective_at=_in_days(5))

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"],
                         "effective_at_before_scheduled_boundary")

    def test_a_close_already_scheduled_cannot_be_moved(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        self.publish(an_agreed_price("retire"), effective_at=_in_days(10))

        response = self.declare(an_agreed_price(
            "reprice", agreed_price_micros=NEW_PRICE),
            effective_at=_in_days(5))

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"],
                         "effective_at_before_scheduled_boundary")
