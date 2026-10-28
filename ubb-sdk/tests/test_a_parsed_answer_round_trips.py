"""Every model the SDK hands back turns back into a dictionary (#596; W5 ruling
13).

`from_wire` used to turn every field a response left out into `None`, at the top
level only and whatever the field's type — so the generated `to_dict()`, which
skips only `UNSET`, called `.to_dict()` on `None` and raised on the
acknowledgement the SDK had just parsed. The rule now reads the DECLARED type:
an omitted field that admits `None` reads `None`; one that does not stays
`UNSET`; a value the response stated is never touched, however falsy — at every
depth a generated model reaches.

Each case calls the real client method a caller would, against a response that
leaves out what the contract lets it leave out, and then `to_dict()`s what came
back.
"""
import unittest
from unittest.mock import MagicMock, patch

from ubb import UNSET, is_unset
from ubb._core.models.task_out import TaskOut
from ubb.metering import MeteringClient
from tests._receipt import A_RECEIPT

#: An acknowledgement carrying only what the contract requires: every optional
#: field is left out, the non-nullable object `grouping_fields` among them.
ACK = {"event_id": "evt_1", "suspended": False, "costing_status": "known",
       "pricing_status": "known", "pricing_status_reason": None,
       "pricing_receipt": A_RECEIPT, "trigger_source": None,
       "stop_bound_micros": None, "stop_measured_micros": None}

#: A unit of work carrying only what the contract requires.
A_TASK = {"task_id": "t1", "status": "completed", "ceiling_status":
          "not_applicable", "control_family": None, "created_at":
          "2026-03-01T00:00:00+00:00", "reason_code": None,
          "recorded_events": 0, "total_billed_cost_micros": 0,
          "total_provider_cost_micros": 0, "trigger_source": None,
          "unpriced_event_count": 0, "unresolved_event_count": 0}

#: A batch item carrying only what the contract requires.
AN_ITEM = {"accepted": True, "pricing_receipt": None,
           "pricing_status_reason": None, "stop_bound_micros": None,
           "stop_measured_micros": None, "trigger_source": None}


def _stated(value):
    """``value`` with every null set aside, at every depth: an omitted field
    whose type admits null reads null after a round trip, which is the rule,
    so what a round trip must keep is everything the response STATED."""
    if isinstance(value, dict):
        return {key: _stated(item) for key, item in value.items()
                if item is not None}
    if isinstance(value, list):
        return [_stated(item) for item in value]
    return value


class _Client(unittest.TestCase):

    def setUp(self):
        self.client = MeteringClient(api_key="k", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()


class EveryAffectedModelRoundTripsTest(_Client):

    @patch("ubb.metering.httpx.Client.post")
    def test_the_acknowledgement_round_trips(self, post):
        """The issue's own repro: `record_usage(...).to_dict()`."""
        post.return_value = MagicMock(status_code=200, json=lambda: ACK)

        ack = self.client.record_usage("c1", "k1", measurements={"calls": 1})

        self.assertIs(ack.grouping_fields, UNSET)
        self.assertIsNone(ack.stop_reason)
        out = ack.to_dict()
        self.assertNotIn("grouping_fields", out)
        self.assertIsNone(out["stop_reason"])
        kept = _stated(out)
        for key, value in _stated(ACK).items():
            self.assertEqual(kept[key], value, key)

    @patch("ubb.metering.httpx.Client.post")
    def test_every_batch_item_round_trips(self, post):
        post.return_value = MagicMock(status_code=200, json=lambda: {
            "accepted": 1, "rejected": 0, "results": [AN_ITEM]})
        from ubb._core.models.usage_batch_item_response import (
            UsageBatchItemResponse)
        from ubb._models import list_from_wire

        self.client.record_batch([{"customer_id": "c1", "idempotency_key": "k1",
                                   "measurements": {"calls": 1}}])
        (item,) = list_from_wire(UsageBatchItemResponse, [AN_ITEM])

        self.assertIs(item.grouping_fields, UNSET)
        self.assertIsNone(item.event_id)
        self.assertNotIn("grouping_fields", item.to_dict())

    @patch("ubb.metering.httpx.Client.get")
    def test_a_task_detail_and_the_work_inside_it_round_trip(self, get):
        """Nested too: the contained unit inside the detail is parsed by the
        same rule, so neither level's `to_dict()` meets a `None` where its
        type promises an object."""
        get.return_value = MagicMock(status_code=200, json=lambda: {
            **A_TASK, "subtasks": [A_TASK]})

        detail = self.client.get_task("t1")

        (inside,) = detail.subtasks
        self.assertIsInstance(inside, TaskOut)
        self.assertIs(detail.grouping_fields, UNSET)
        self.assertIs(inside.grouping_fields, UNSET)
        self.assertIsNone(inside.completed_at)
        out = detail.to_dict()
        self.assertNotIn("grouping_fields", out["subtasks"][0])
        self.assertIsNone(out["subtasks"][0]["completed_at"])

    @patch("ubb.metering.httpx.Client.get")
    def test_a_detail_that_left_out_its_contained_work_round_trips(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: A_TASK)

        detail = self.client.get_task("t1")

        self.assertIs(detail.subtasks, UNSET)
        self.assertNotIn("subtasks", detail.to_dict())

    @patch("ubb.metering.httpx.Client.get")
    def test_a_page_of_work_round_trips(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [A_TASK], "next_cursor": None, "has_more": False})

        (task,) = self.client.list_tasks().data

        self.assertIs(task.grouping_fields, UNSET)
        self.assertEqual(task.to_dict()["task_id"], "t1")


class OmittedNullAndFalsyAreThreeFactsTest(_Client):
    """Ruling 13: never conflated, and never by `not x`."""

    @patch("ubb.metering.httpx.Client.post")
    def test_a_falsy_value_the_response_stated_is_kept(self, post):
        post.return_value = MagicMock(status_code=200, json=lambda: {
            **ACK, "billed_cost_micros": 0, "stop": False,
            "uncosted_measurement_keys": [], "stop_reason": "",
            "grouping_fields": {}})

        ack = self.client.record_usage("c1", "k1", measurements={"calls": 1})

        self.assertEqual(ack.billed_cost_micros, 0)
        self.assertIsNot(ack.billed_cost_micros, None)
        self.assertIs(ack.stop, False)
        self.assertEqual(ack.uncosted_measurement_keys, [])
        self.assertFalse(is_unset(ack.uncosted_measurement_keys))
        self.assertEqual(ack.stop_reason, "")
        out = ack.to_dict()
        self.assertEqual((out["billed_cost_micros"], out["stop"],
                          out["uncosted_measurement_keys"], out["stop_reason"],
                          out["grouping_fields"]), (0, False, [], "", {}))

    @patch("ubb.metering.httpx.Client.post")
    def test_an_omitted_list_is_unset_and_a_stated_empty_one_is_not(self, post):
        """The reason `not x` is never the test: both read falsy."""
        post.return_value = MagicMock(status_code=200, json=lambda: ACK)
        omitted = self.client.record_usage("c1", "k1", measurements={"calls": 1})
        post.return_value = MagicMock(status_code=200, json=lambda: {
            **ACK, "uncosted_measurement_keys": []})
        stated = self.client.record_usage("c1", "k2", measurements={"calls": 1})

        self.assertTrue(is_unset(omitted.uncosted_measurement_keys))
        self.assertFalse(is_unset(stated.uncosted_measurement_keys))
        self.assertFalse(omitted.uncosted_measurement_keys)
        self.assertFalse(stated.uncosted_measurement_keys)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_stated_null_and_an_omitted_nullable_field_read_alike(self, post):
        post.return_value = MagicMock(status_code=200, json=lambda: {
            **ACK, "stop_reason": None})
        stated = self.client.record_usage("c1", "k1", measurements={"calls": 1})
        post.return_value = MagicMock(status_code=200, json=lambda: ACK)
        omitted = self.client.record_usage("c1", "k2", measurements={"calls": 1})

        self.assertIsNone(stated.stop_reason)
        self.assertIsNone(omitted.stop_reason)
