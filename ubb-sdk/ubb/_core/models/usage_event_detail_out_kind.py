from enum import Enum

class UsageEventDetailOutKind(str, Enum):
    METERED_USAGE = "metered_usage"
    TASK_CHARGE = "task_charge"

    def __str__(self) -> str:
        return str(self.value)
