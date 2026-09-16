from enum import Enum

class EconomicMeasureOutStatus(str, Enum):
    INCOMPLETE = "incomplete"
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE_AT_REQUESTED_GRAIN = "unavailable_at_requested_grain"
    UNAVAILABLE_OUTSIDE_RETENTION_HORIZON = "unavailable_outside_retention_horizon"

    def __str__(self) -> str:
        return str(self.value)
