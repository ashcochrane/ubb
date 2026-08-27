from enum import Enum

class TaskTypeOutKind(str, Enum):
    SUBTASK = "subtask"
    TASK = "task"

    def __str__(self) -> str:
        return str(self.value)
