"""A recorded quantity leaves the SDK as canonical exact text (#603, ADR-0020).

The recording request types every quantity as an exact decimal STRING and
refuses a JSON number, because in most clients a JSON number has already been a
binary float. So the facade takes what a caller exactly has — an ``int``, a
``decimal.Decimal`` or a string — and sends its canonical text; a ``float``
or a ``bool`` is refused before anything is sent. ``record_batch`` holds every
item to the same rule and names the item it refuses.
"""
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from ubb.exceptions import UBBValidationError
from ubb.metering import MeteringClient

#: An acknowledgement carrying every required key, so the generated model
#: parses it: the stop facts (#569) and the price status's reason (#603) are
#: required and nullable.
ACK = {"event_id": "evt_1", "suspended": False, "costing_status": "known",
       "pricing_status": "known", "pricing_status_reason": None,
       "trigger_source": None, "stop_bound_micros": None,
       "stop_measured_micros": None}

#: What a caller passes, and the text that goes on the wire.
SENT_AS = {
    12: "12",
    -3: "-3",
    0: "0",
    2 ** 53 + 1: "9007199254740993",
    10 ** 60: "1" + "0" * 60,
    Decimal("2.5"): "2.5",
    Decimal("-0.50"): "-0.5",
    Decimal("1E+3"): "1000",
    Decimal("0.000000000000000000000000000000000000001"):
        "0.000000000000000000000000000000000000001",
    Decimal("-0"): "0",
    "12": "12",
    "007": "7",
    "01.500": "1.5",
    "-0.000": "0",
    "123456789012345678901234567890.123456789012345678901234567890":
        "123456789012345678901234567890.12345678901234567890123456789",
}

#: What is refused before anything is sent.
REFUSED = {
    "a float": 2.5,
    "a whole float": 2.0,
    "True": True,
    "False": False,
    "None": None,
    "a NaN Decimal": Decimal("NaN"),
    "an infinite Decimal": Decimal("Infinity"),
    "an exponent": "1e3",
    "a leading plus": "+1",
    "whitespace": " 1",
    "a separator": "1_000",
    "no digit before the point": ".5",
    "empty text": "",
    "a list": [1],
}


class RecordUsageSendsExactTextTest(unittest.TestCase):

    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test",
                                     base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_each_exact_value_is_sent_as_its_canonical_text(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: ACK)
        for value, text in SENT_AS.items():
            with self.subTest(value=value):
                self.client.record_usage("c1", "k1",
                                         measurements={"calls": value})
                body = mock_post.call_args.kwargs["json"]
                self.assertEqual(body["measurements"], {"calls": text})
                self.assertIsInstance(body["measurements"]["calls"], str)

    @patch("ubb.metering.httpx.Client.post")
    def test_an_int_past_cpythons_text_conversion_is_sent_whole(self,
                                                                mock_post):
        """A quantity has no digit bound, and CPython refuses `str()` of an
        int longer than 4,300 digits (`sys.get_int_max_str_digits`), so the
        SDK never asks it to."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: ACK)
        for value, text in ((10 ** 5000 + 7, "1" + "0" * 4999 + "7"),
                            (-(10 ** 5000), "-1" + "0" * 5000)):
            with self.subTest(sign=text[0]):
                self.client.record_usage("c1", "k1",
                                         measurements={"calls": value})
                body = mock_post.call_args.kwargs["json"]
                self.assertEqual(body["measurements"], {"calls": text})

    @patch("ubb.metering.httpx.Client.post")
    def test_a_float_or_a_flag_is_refused_and_nothing_is_sent(self, mock_post):
        for why, value in REFUSED.items():
            with self.subTest(why=why):
                with self.assertRaises(UBBValidationError) as refused:
                    self.client.record_usage("c1", "k1",
                                             measurements={"calls": value})
                self.assertIn("calls", str(refused.exception))
                self.assertIn("Nothing was sent", str(refused.exception))
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_a_float_refusal_says_what_to_send_instead(self, mock_post):
        with self.assertRaises(UBBValidationError) as refused:
            self.client.record_usage("c1", "k1", measurements={"s": 0.1})
        said = str(refused.exception)
        self.assertIn("decimal.Decimal", said)
        self.assertIn("string", said)
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_no_bag_sends_no_key(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: ACK)
        self.client.record_usage("c1", "k1")
        self.assertNotIn("measurements", mock_post.call_args.kwargs["json"])


class RecordBatchSendsExactTextTest(unittest.TestCase):

    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test",
                                     base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_every_item_is_sent_as_canonical_text(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [], "accepted": 0, "rejected": 0})
        self.client.record_batch([
            {"customer_id": "c1", "idempotency_key": "a",
             "measurements": {"calls": 3, "seconds": Decimal("2.50")}},
            {"customer_id": "c1", "idempotency_key": "b",
             "measurements": {"calls": "-0004"}},
            {"customer_id": "c1", "idempotency_key": "c"},
        ])
        events = mock_post.call_args.kwargs["json"]["events"]
        self.assertEqual(events[0]["measurements"],
                         {"calls": "3", "seconds": "2.5"})
        self.assertEqual(events[1]["measurements"], {"calls": "-4"})
        self.assertNotIn("measurements", events[2])

    @patch("ubb.metering.httpx.Client.post")
    def test_a_float_in_any_item_refuses_the_batch_naming_the_item(
            self, mock_post):
        with self.assertRaises(UBBValidationError) as refused:
            self.client.record_batch([
                {"customer_id": "c1", "idempotency_key": "a",
                 "measurements": {"calls": "1"}},
                {"customer_id": "c1", "idempotency_key": "b",
                 "measurements": {"seconds": 2.5}},
            ])
        self.assertIn("events[1]", str(refused.exception))
        self.assertIn("seconds", str(refused.exception))
        mock_post.assert_not_called()
