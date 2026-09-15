from enum import Enum

class AttributedSuppliedRevenueOutRecognitionMethod(str, Enum):
    ON_RECEIPT = "on_receipt"
    STRAIGHT_LINE = "straight_line"

    def __str__(self) -> str:
        return str(self.value)
