from enum import Enum

class TaskTypeInPricingModeType0(str, Enum):
    EVENT_PRICED = "event_priced"
    FIXED = "fixed"

    def __str__(self) -> str:
        return str(self.value)
