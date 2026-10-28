from enum import Enum

class ProgramOutStatus(str, Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    PAUSED = "paused"

    def __str__(self) -> str:
        return str(self.value)
