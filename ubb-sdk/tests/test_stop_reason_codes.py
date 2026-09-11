"""The metering client exposes the seven known stop reasons from the generated
vocabulary, and the stop signal's reason is documented against them (#457,
slice 6 §17 — the `reason_code` SDK payment).

An integrator branches on a constant and never parses a string. The value
stays a string on the wire and an unknown one still travels: the set is open,
and the client validates nothing.
"""
import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ubb.metering as metering
import ubb.vocabulary as vocabulary
from ubb.exceptions import UBBStopRequested
from ubb.metering import MeteringClient

#: Every generated handle for one concept, derived from the artifact rather
#: than listed — an eighth registry value is a red line here, not a silent
#: partial payment.
REASON_CODE_NAMES = frozenset(
    name for name in vars(vocabulary)
    if name.startswith("REASON_CODE_") and not name.endswith("_KNOWN_VALUES"))


class TheClientHoldsTheSevenTest(unittest.TestCase):
    def test_every_known_reason_is_reachable_from_the_metering_module(self):
        for name in REASON_CODE_NAMES:
            self.assertIs(getattr(metering, name), getattr(vocabulary, name),
                          name)

    def test_the_set_is_the_generated_whole_set(self):
        self.assertIs(metering.STOP_REASON_CODES,
                      vocabulary.REASON_CODE_KNOWN_VALUES)
        self.assertEqual(metering.STOP_REASON_CODES,
                         {getattr(vocabulary, n) for n in REASON_CODE_NAMES})
        self.assertGreater(len(metering.STOP_REASON_CODES), 0)

    def test_the_module_imports_them_by_reference(self):
        """Read the import statement, not the values: a literal that happened
        to agree would satisfy an equality and is exactly the debt this pays."""
        tree = ast.parse(Path(metering.__file__).read_text(encoding="utf-8"))
        imported = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "ubb.vocabulary"
            for alias in node.names if alias.name.startswith("REASON_CODE_")}
        self.assertEqual(imported,
                         REASON_CODE_NAMES | {"REASON_CODE_KNOWN_VALUES"})

    def test_the_stop_signal_is_documented_against_them(self):
        self.assertIn("STOP_REASON_CODES", MeteringClient.record_usage.__doc__)
        self.assertIn("STOP_REASON_CODES", UBBStopRequested.__doc__)


class AnUnknownReasonStillTravelsTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x",
                                     base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_a_reason_this_client_has_never_seen_reaches_the_signal(self,
                                                                    mock_post):
        unseen = "a_reason_ubb_has_not_shipped_yet"
        self.assertNotIn(unseen, metering.STOP_REASON_CODES)
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "costing_status": "known",
            "pricing_status": "known", "stop": True, "stop_reason": unseen,
            "stop_scope": "task"})
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        self.assertEqual(cm.exception.stop_reason, unseen)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_known_reason_compares_equal_to_its_constant(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "costing_status": "known",
            "pricing_status": "known", "stop": True,
            "stop_reason": vocabulary.REASON_CODE_TASK_COGS_CEILING,
            "stop_scope": "subtask"})
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        self.assertEqual(cm.exception.stop_reason,
                         metering.REASON_CODE_TASK_COGS_CEILING)
        self.assertIn(cm.exception.stop_reason, metering.STOP_REASON_CODES)


if __name__ == "__main__":
    unittest.main()
