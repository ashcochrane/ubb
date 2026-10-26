from enum import Enum

class UnresolvedQueueRowUnresolvedReasonType0(str, Enum):
    COST_RATE_MISSING = "cost_rate_missing"
    EVENT_TYPE_NOT_DECLARED = "event_type_not_declared"
    MEASUREMENT_NOT_DECLARED = "measurement_not_declared"
    REPORTED_COST_MISSING = "reported_cost_missing"

    def __str__(self) -> str:
        return str(self.value)
