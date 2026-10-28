from enum import Enum

class GrantOutStatus(str, Enum):
    ACTIVE = "active"
    DEPLETED = "depleted"
    EXPIRED = "expired"
    VOIDED = "voided"

    def __str__(self) -> str:
        return str(self.value)
