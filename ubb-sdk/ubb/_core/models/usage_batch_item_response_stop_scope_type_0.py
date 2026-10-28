from enum import Enum

class UsageBatchItemResponseStopScopeType0(str, Enum):
    CUSTOMER = "customer"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
