from enum import Enum

class GroupingFieldInScope(str, Enum):
    EVENT = "event"
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
