from enum import Enum

class CloseTaskResponseStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
    KILLED = "killed"

    def __str__(self) -> str:
        return str(self.value)
