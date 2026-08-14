from enum import Enum

class RecordUsageResponseUnresolvedReasonType0(str, Enum):
    COST_RATE_MISSING = "cost_rate_missing"
    MEASUREMENT_NOT_DECLARED = "measurement_not_declared"
    REPORTED_COST_MISSING = "reported_cost_missing"

    def __str__(self) -> str:
        return str(self.value)
