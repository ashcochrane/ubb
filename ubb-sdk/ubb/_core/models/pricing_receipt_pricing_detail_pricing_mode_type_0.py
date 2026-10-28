from enum import Enum

class PricingReceiptPricingDetailPricingModeType0(str, Enum):
    EVENT_PRICED = "event_priced"
    FIXED = "fixed"

    def __str__(self) -> str:
        return str(self.value)
