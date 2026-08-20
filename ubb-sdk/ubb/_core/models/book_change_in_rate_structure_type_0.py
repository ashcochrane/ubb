from enum import Enum

class BookChangeInRateStructureType0(str, Enum):
    FIXED_COMPONENT = "fixed_component"
    PER_UNIT = "per_unit"

    def __str__(self) -> str:
        return str(self.value)
