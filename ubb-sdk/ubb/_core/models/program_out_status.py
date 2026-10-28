from enum import Enum

class ProgramOutStatus(str, Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"

    def __str__(self) -> str:
        return str(self.value)
