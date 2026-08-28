from enum import Enum

class CloseTaskRequestOutcome(str, Enum):
    CANCELLED = "cancelled"
    DELIVERED = "delivered"
    FAILED = "failed"

    def __str__(self) -> str:
        return str(self.value)
