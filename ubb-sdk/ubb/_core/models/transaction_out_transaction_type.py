from enum import Enum

class TransactionOutTransactionType(str, Enum):
    ADJUSTMENT = "adjustment"
    DEBIT = "debit"
    DISPUTE_DEDUCTION = "dispute_deduction"
    GRANT = "grant"
    GRANT_EXPIRY = "grant_expiry"
    GRANT_VOID = "grant_void"
    REFUND = "refund"
    STRIPE_REFUND = "stripe_refund"
    TOP_UP = "top_up"
    USAGE_DEDUCTION = "usage_deduction"
    WITHDRAWAL = "withdrawal"

    def __str__(self) -> str:
        return str(self.value)
