from enum import Enum

class RecordUsageResponsePricingStatus(str, Enum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    WAIVED = "waived"

    def __str__(self) -> str:
        return str(self.value)
