from enum import Enum

class TaskTypeOutPricingMode(str, Enum):
    EVENT_PRICED = "event_priced"
    FIXED = "fixed"

    def __str__(self) -> str:
        return str(self.value)
