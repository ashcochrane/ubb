from enum import Enum

class UsageBatchItemResponsePricingStatusReasonType0(str, Enum):
    EVENT_TYPE_NOT_DECLARED = "event_type_not_declared"
    MEASUREMENT_NOT_DECLARED = "measurement_not_declared"
    NEGATIVE_PRICE_UNSUPPORTED = "negative_price_unsupported"

    def __str__(self) -> str:
        return str(self.value)
