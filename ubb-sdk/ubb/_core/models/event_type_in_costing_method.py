from enum import Enum

class EventTypeInCostingMethod(str, Enum):
    CALCULATED = "calculated"
    REPORTED = "reported"

    def __str__(self) -> str:
        return str(self.value)
