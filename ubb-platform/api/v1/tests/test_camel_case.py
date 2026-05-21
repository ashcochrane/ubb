from django.test import TestCase
from api.v1.middleware import to_camel_case, transform_keys


class CamelCaseUnitTest(TestCase):
    def test_simple_key(self):
        self.assertEqual(to_camel_case("revenue_micros"), "revenueMicros")

    def test_single_word(self):
        self.assertEqual(to_camel_case("id"), "id")

    def test_multiple_underscores(self):
        self.assertEqual(to_camel_case("cost_per_unit_micros"), "costPerUnitMicros")

    def test_empty_string(self):
        self.assertEqual(to_camel_case(""), "")

    def test_nested_dict(self):
        data = {
            "revenue_micros": 100,
            "nested_object": {"inner_key": "value"},
            "list_field": [{"item_key": 1}],
        }
        result = transform_keys(data, to_camel_case)
        self.assertEqual(result, {
            "revenueMicros": 100,
            "nestedObject": {"innerKey": "value"},
            "listField": [{"itemKey": 1}],
        })

    def test_preserves_non_dict_values(self):
        data = {"cost_per_unit_micros": 75000, "name": "test"}
        result = transform_keys(data, to_camel_case)
        self.assertEqual(result["costPerUnitMicros"], 75000)
        self.assertEqual(result["name"], "test")

    def test_usage_metrics_keys_preserved(self):
        """usage_metrics has dynamic keys (metric names) that must NOT be transformed."""
        data = {
            "event_type": "llm_call",
            "usage_metrics": {"input_tokens": 1000, "output_tokens": 500},
        }
        result = transform_keys(data, to_camel_case)
        self.assertEqual(result["eventType"], "llm_call")
        # usage_metrics key is transformed, but its children keys are preserved
        self.assertIn("usageMetrics", result)
        self.assertIn("input_tokens", result["usageMetrics"])
        self.assertIn("output_tokens", result["usageMetrics"])
        self.assertNotIn("inputTokens", result["usageMetrics"])

    def test_card_dimensions_keys_preserved(self):
        """card_dimensions uses card slugs as keys — preserve them."""
        data = {
            "card_dimensions": {"gemini_2_flash": ["input_tokens", "output_tokens"]},
            "dimension_prices": {
                "input_tokens": {"cost_per_unit_micros": 75000, "unit_quantity": 1000000},
            },
        }
        result = transform_keys(data, to_camel_case)
        self.assertIn("cardDimensions", result)
        self.assertIn("gemini_2_flash", result["cardDimensions"])
        self.assertNotIn("gemini2Flash", result["cardDimensions"])
        self.assertIn("dimensionPrices", result)
        self.assertIn("input_tokens", result["dimensionPrices"])

    def test_stacked_series_data_keys_preserved(self):
        """Stacked series data rows use group/card slugs as keys — preserve them."""
        data = {
            "cost_by_group": {
                "series": [{"key": "research_agent"}, {"key": "chat"}],
                "data": [
                    {"date": "2026-04-01", "research_agent": 5000, "chat": 3000},
                ],
            },
        }
        result = transform_keys(data, to_camel_case)
        self.assertIn("costByGroup", result)
        row = result["costByGroup"]["data"][0]
        self.assertIn("research_agent", row)
        self.assertIn("chat", row)
        self.assertNotIn("researchAgent", row)
