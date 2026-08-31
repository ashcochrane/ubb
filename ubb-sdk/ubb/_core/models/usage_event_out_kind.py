from enum import Enum

class UsageEventOutKind(str, Enum):
    METERED_USAGE = "metered_usage"
    TASK_CHARGE = "task_charge"

    def __str__(self) -> str:
        return str(self.value)
