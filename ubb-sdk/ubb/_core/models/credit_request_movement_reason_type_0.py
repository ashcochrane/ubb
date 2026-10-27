from enum import Enum

class CreditRequestMovementReasonType0(str, Enum):
    CHARGEBACK = "chargeback"
    CORRECTION = "correction"
    GOODWILL = "goodwill"
    MIGRATION = "migration"
    OTHER = "other"
    WRITE_OFF = "write_off"

    def __str__(self) -> str:
        return str(self.value)
