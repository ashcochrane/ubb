from enum import Enum

class TopUpAcceptedResponseStatus(str, Enum):
    TOPUP_REQUESTED = "topup_requested"

    def __str__(self) -> str:
        return str(self.value)
