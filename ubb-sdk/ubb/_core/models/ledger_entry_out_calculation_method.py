from enum import Enum

class LedgerEntryOutCalculationMethod(str, Enum):
    ACTUAL_COST = "actual_cost"
    ESTIMATED_COST = "estimated_cost"
    FLAT_FEE = "flat_fee"

    def __str__(self) -> str:
        return str(self.value)
