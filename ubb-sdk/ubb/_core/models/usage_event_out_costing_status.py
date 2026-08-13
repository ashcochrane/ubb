from enum import Enum

class UsageEventOutCostingStatus(str, Enum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"

    def __str__(self) -> str:
        return str(self.value)
