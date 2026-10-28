from enum import Enum

class CeilingEpisodeRowStopScope(str, Enum):
    CUSTOMER = "customer"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
