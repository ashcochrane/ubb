from enum import Enum

class BusinessMarginOutBasis(str, Enum):
    RECOGNISED = "recognised"

    def __str__(self) -> str:
        return str(self.value)
