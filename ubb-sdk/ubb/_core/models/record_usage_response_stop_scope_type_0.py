from enum import Enum

class RecordUsageResponseStopScopeType0(str, Enum):
    CUSTOMER = "customer"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
