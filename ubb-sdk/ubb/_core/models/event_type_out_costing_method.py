from enum import Enum

class EventTypeOutCostingMethod(str, Enum):
    CALCULATED = "calculated"
    REPORTED = "reported"

    def __str__(self) -> str:
        return str(self.value)
