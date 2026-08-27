from enum import Enum

class TaskTypeInKind(str, Enum):
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
