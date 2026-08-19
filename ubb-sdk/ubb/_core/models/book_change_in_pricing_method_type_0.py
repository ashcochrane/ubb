from enum import Enum

class BookChangeInPricingMethodType0(str, Enum):
    DIRECT_EVENT_PRICE = "direct_event_price"
    MARGIN_OVER_COST = "margin_over_cost"

    def __str__(self) -> str:
        return str(self.value)
