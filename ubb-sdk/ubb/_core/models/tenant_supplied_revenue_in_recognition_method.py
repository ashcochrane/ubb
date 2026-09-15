from enum import Enum

class TenantSuppliedRevenueInRecognitionMethod(str, Enum):
    ON_RECEIPT = "on_receipt"
    STRAIGHT_LINE = "straight_line"

    def __str__(self) -> str:
        return str(self.value)
