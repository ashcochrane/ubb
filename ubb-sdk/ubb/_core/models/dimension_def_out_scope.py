from enum import Enum

class DimensionDefOutScope(str, Enum):
    EVENT = "event"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
