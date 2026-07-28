from enum import Enum

class PlanInInterval(str, Enum):
    MONTH = "month"
    YEAR = "year"

    def __str__(self) -> str:
        return str(self.value)
