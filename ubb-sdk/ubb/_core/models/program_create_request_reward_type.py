from enum import Enum

class ProgramCreateRequestRewardType(str, Enum):
    FLAT_FEE = "flat_fee"
    PROFIT_SHARE = "profit_share"
    REVENUE_SHARE = "revenue_share"

    def __str__(self) -> str:
        return str(self.value)
