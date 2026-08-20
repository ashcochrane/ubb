from enum import Enum

class RateOutRateStructure(str, Enum):
    FIXED_COMPONENT = "fixed_component"
    PER_UNIT = "per_unit"

    def __str__(self) -> str:
        return str(self.value)
