from enum import Enum

class BusinessMarginOutBasis(str, Enum):
    RECOGNISED = "recognised"
    RECORDED = "recorded"

    def __str__(self) -> str:
        return str(self.value)
