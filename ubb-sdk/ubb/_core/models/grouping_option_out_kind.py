from enum import Enum

class GroupingOptionOutKind(str, Enum):
    FIELD = "field"
    ROLLUP = "rollup"

    def __str__(self) -> str:
        return str(self.value)
