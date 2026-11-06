from enum import Enum

class MeUsageInvoiceOutStatus(str, Enum):
    FAILED = "failed"
    FAILED_PERMANENT = "failed_permanent"
    PENDING = "pending"
    PUSHED = "pushed"
    PUSHING = "pushing"
    SKIPPED = "skipped"

    def __str__(self) -> str:
        return str(self.value)
