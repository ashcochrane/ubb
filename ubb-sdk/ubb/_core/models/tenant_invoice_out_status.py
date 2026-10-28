from enum import Enum

class TenantInvoiceOutStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"

    def __str__(self) -> str:
        return str(self.value)
