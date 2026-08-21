from enum import Enum

class UsageEventDetailOutPricingReceiptSubjectTypeType0(str, Enum):
    CHARGE = "charge"
    USAGE_EVENT = "usage_event"

    def __str__(self) -> str:
        return str(self.value)
