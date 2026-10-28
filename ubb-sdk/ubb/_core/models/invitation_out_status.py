from enum import Enum

class InvitationOutStatus(str, Enum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    REVOKED = "revoked"

    def __str__(self) -> str:
        return str(self.value)
