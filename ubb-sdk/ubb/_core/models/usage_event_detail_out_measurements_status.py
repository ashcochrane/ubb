from enum import Enum

class UsageEventDetailOutMeasurementsStatus(str, Enum):
    AVAILABLE = "available"
    NOT_APPLICABLE = "not_applicable"
    PRUNED = "pruned"

    def __str__(self) -> str:
        return str(self.value)
