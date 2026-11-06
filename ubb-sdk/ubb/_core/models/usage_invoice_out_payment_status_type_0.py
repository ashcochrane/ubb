from enum import Enum

class UsageInvoiceOutPaymentStatusType0(str, Enum):
    OPEN = "open"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"

    def __str__(self) -> str:
        return str(self.value)
