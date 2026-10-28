from enum import Enum

class UnprofitableOutBasis(str, Enum):
    RECOGNISED = "recognised"

    def __str__(self) -> str:
        return str(self.value)
