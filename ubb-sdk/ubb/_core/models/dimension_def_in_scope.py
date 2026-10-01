from enum import Enum

class DimensionDefInScope(str, Enum):
    EVENT = "event"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
