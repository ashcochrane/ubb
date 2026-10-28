from enum import Enum

class TenantInvoiceOutStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"

    def __str__(self) -> str:
        return str(self.value)
