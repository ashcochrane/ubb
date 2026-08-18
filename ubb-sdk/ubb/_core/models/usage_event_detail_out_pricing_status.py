from enum import Enum

class UsageEventDetailOutPricingStatus(str, Enum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    WAIVED = "waived"

    def __str__(self) -> str:
        return str(self.value)
