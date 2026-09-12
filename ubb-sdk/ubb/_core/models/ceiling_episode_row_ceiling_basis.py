from enum import Enum

class CeilingEpisodeRowCeilingBasis(str, Enum):
    COST = "cost"
    TIME = "time"

    def __str__(self) -> str:
        return str(self.value)
