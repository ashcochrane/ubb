from enum import Enum

class MeEconomicsOutBasis(str, Enum):
    RECORDED = "recorded"

    def __str__(self) -> str:
        return str(self.value)
