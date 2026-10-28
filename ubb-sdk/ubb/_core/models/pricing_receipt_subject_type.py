from enum import Enum

class PricingReceiptSubjectType(str, Enum):
    CHARGE = "charge"
    USAGE_EVENT = "usage_event"

    def __str__(self) -> str:
        return str(self.value)
