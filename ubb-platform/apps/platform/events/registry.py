"""
Handler registration for outbox event processing.

Products register handlers in AppConfig.ready() with:
    registry.register("usage.recorded", "billing.wallet_deduction", handler_fn, requires_product="billing")
"""


class HandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, list[dict]] = {}

    def register(self, event_type: str, name: str, handler, requires_product: str | None = None):
        self._handlers.setdefault(event_type, []).append({
            "name": name,
            "handler": handler,
            "requires_product": requires_product,
        })

    def get_handlers(self, event_type: str) -> list[dict]:
        return self._handlers.get(event_type, [])


# Singleton — products register here in AppConfig.ready()
handler_registry = HandlerRegistry()
