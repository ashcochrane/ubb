"""Snake-case to camelCase key transformation for API responses.

Dynamic-key fields (usage_metrics, card_dimensions, dimension_prices, dimensions,
metadata, properties, pricing_provenance, and stacked-series 'data' rows) are
preserved as-is because their keys are user-defined values (metric names, card
slugs, group slugs) that must match what the SDK/UI sends.
"""

import json

from ninja.renderers import JSONRenderer


def to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    if not snake_str or "_" not in snake_str:
        return snake_str
    parts = snake_str.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:] if p)


# Keys whose VALUES are dicts with dynamic/user-defined keys that should NOT
# be transformed. The values inside these dicts still get recursed for nested
# schema dicts, but the top-level keys of the value dict are preserved.
_DYNAMIC_KEY_FIELDS = frozenset({
    "usage_metrics", "usageMetrics",
    "card_dimensions", "cardDimensions",
    "dimension_prices", "dimensionPrices",
    "dimensions",
    "metadata",
    "properties",
    "pricing_provenance", "pricingProvenance",
    "sparklines",
})


def transform_keys(obj, fn, _preserve_keys=False):
    """Recursively transform dict keys using fn.

    When _preserve_keys is True, dict keys at this level are NOT transformed
    (used for dynamic-key fields like usage_metrics, card_dimensions, etc.).
    Nested values still get normal transformation.
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            new_key = k if _preserve_keys else fn(k)
            # Check if this key's value has dynamic keys
            if k in _DYNAMIC_KEY_FIELDS or new_key in _DYNAMIC_KEY_FIELDS:
                # Preserve the dict keys one level down, but still recurse values
                result[new_key] = transform_keys(v, fn, _preserve_keys=True)
            elif k == "data" and isinstance(v, list) and v and isinstance(v[0], dict) and "date" in v[0]:
                # Stacked series 'data' arrays: rows have dynamic keys (group/card slugs)
                # Preserve the row keys but recurse normally into nested values
                result[new_key] = [transform_keys(row, fn, _preserve_keys=True) for row in v]
            else:
                result[new_key] = transform_keys(v, fn)
        return result
    if isinstance(obj, list):
        return [transform_keys(item, fn) for item in obj]
    return obj


class CamelCaseRenderer(JSONRenderer):
    def render(self, request, data, *, response_status):
        if isinstance(data, (dict, list)):
            data = transform_keys(data, to_camel_case)
        return super().render(request, data, response_status=response_status)
