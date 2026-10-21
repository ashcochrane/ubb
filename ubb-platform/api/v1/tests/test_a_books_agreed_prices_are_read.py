"""A Pricing Book's agreed prices are read through a typed read of their own
(#553, spec stories 13 and 26).

`GET /pricing/books/{book_id}/agreed-prices` is the rates read's sibling: the
same three questions — what is open, every version, what was in force at one
instant — paginated, under its own operationId. What is asked here is what
only the route can answer: the fields it publishes, the half-open `as_of`, the
history a reprice leaves, the cursor, and which ids it answers for. Who may
read it is held with the other Pricing Book routes in `test_book_api.py`.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.v1.tests.test_an_agreed_price_is_declared_through_the_publish_act import (
    PRICE, NEW_PRICE, SOLD_PER_EVENT, SOLD_WHOLE, _APricingBookMixin,
    an_agreed_price)
from apps.platform.tenants.models import Tenant, TenantApiKey

FIELDS = {"id", "book_id", "lineage_id", "task_type", "agreed_price_micros",
          "valid_from", "valid_to"}


class ABooksAgreedPricesAreReadTest(_APricingBookMixin, TestCase):

    def read(self, **params):
        query = "&".join(f"{name}={value}" for name, value in params.items())
        return self._ok("get", f"/api/v1/metering/pricing/books/"
                               f"{self.book['id']}/agreed-prices?{query}")

    def test_a_line_reads_back_with_exactly_the_published_fields(self):
        (opened,) = self.publish(an_agreed_price(
            "add", agreed_price_micros=PRICE))["opened_agreed_price_ids"]

        (line,) = self.read()["data"]

        self.assertEqual(set(line), FIELDS)
        self.assertEqual(line["id"], opened)
        self.assertEqual(line["book_id"], self.book["id"])
        self.assertEqual(line["task_type"], SOLD_WHOLE)
        self.assertEqual(line["agreed_price_micros"], PRICE)
        self.assertIsNone(line["valid_to"])

    def test_by_default_the_open_lines_including_one_scheduled_to_open(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        self.publish(an_agreed_price("add", SOLD_PER_EVENT,
                                     agreed_price_micros=NEW_PRICE),
                     effective_at=timezone.now() + timedelta(days=3))

        self.assertEqual({line["task_type"] for line in self.read()["data"]},
                         {SOLD_WHOLE, SOLD_PER_EVENT})

    def test_history_keeps_the_line_a_reprice_closed(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        self.publish(an_agreed_price("reprice", agreed_price_micros=NEW_PRICE))

        open_now = self.read()["data"]
        every_version = self.read(include_history="true")["data"]

        self.assertEqual([line["agreed_price_micros"] for line in open_now],
                         [NEW_PRICE])
        self.assertEqual(
            sorted(line["agreed_price_micros"] for line in every_version),
            sorted([PRICE, NEW_PRICE]))
        self.assertEqual(len({line["lineage_id"] for line in every_version}),
                         1)

    def test_as_of_answers_the_line_in_force_at_that_instant(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        boundary = timezone.now() + timedelta(days=5)
        self.publish(an_agreed_price("reprice", agreed_price_micros=NEW_PRICE),
                     effective_at=boundary)

        def at(instant):
            return [line["agreed_price_micros"] for line in
                    self.read(as_of=instant.isoformat().replace("+", "%2B"))
                    ["data"]]

        self.assertEqual(at(boundary - timedelta(seconds=1)), [PRICE])
        # Half-open: at the boundary itself the successor is in force.
        self.assertEqual(at(boundary), [NEW_PRICE])
        self.assertEqual(at(boundary + timedelta(days=1)), [NEW_PRICE])

    def test_as_of_before_any_line_opened_answers_nothing(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE),
                     effective_at=timezone.now() + timedelta(days=2))

        self.assertEqual(
            self.read(as_of=timezone.now().isoformat().replace("+", "%2B"))
            ["data"], [])

    def test_the_read_is_paginated_newest_first(self):
        self.publish(an_agreed_price("add", agreed_price_micros=PRICE))
        self.publish(an_agreed_price("add", SOLD_PER_EVENT,
                                     agreed_price_micros=NEW_PRICE))

        first = self.read(limit=1)
        second = self.read(limit=1, cursor=first["next_cursor"])

        self.assertTrue(first["has_more"])
        self.assertEqual([line["task_type"] for line in first["data"]],
                         [SOLD_PER_EVENT])
        self.assertEqual([line["task_type"] for line in second["data"]],
                         [SOLD_WHOLE])
        self.assertFalse(second["has_more"])

    def test_a_cost_book_holds_no_agreed_price(self):
        cost_book = self._ok("post", "/api/v1/metering/pricing/cost-books",
                             {"provider_key": "openai", "key": "openai",
                              "is_default": True})

        response = self._send(
            "get", f"/api/v1/metering/pricing/books/{cost_book['id']}"
                   f"/agreed-prices")

        self.assertEqual(response.status_code, 404, response.content)

    def test_another_tenants_book_is_not_found(self):
        other = Tenant.objects.create(name="Other",
                                      products=["metering", "billing"])
        _, other_key = TenantApiKey.create_key(other)

        response = self.http.get(
            f"/api/v1/metering/pricing/books/{self.book['id']}/agreed-prices",
            HTTP_AUTHORIZATION=f"Bearer {other_key}")

        self.assertEqual(response.status_code, 404, response.content)
