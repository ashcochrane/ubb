from enum import Enum

class TenantBillingPeriodOutStatus(str, Enum):
    CLOSED = "closed"
    INVOICED = "invoiced"
    INVOICING = "invoicing"
    OPEN = "open"

    def __str__(self) -> str:
        return str(self.value)
