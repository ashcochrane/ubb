from enum import Enum

class UnresolvedQueueRowPricingStatusReasonType0(str, Enum):
    NEGATIVE_PRICE_UNSUPPORTED = "negative_price_unsupported"

    def __str__(self) -> str:
        return str(self.value)
