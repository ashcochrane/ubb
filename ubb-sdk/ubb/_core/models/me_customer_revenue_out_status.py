from enum import Enum

class MeCustomerRevenueOutStatus(str, Enum):
    INCOMPLETE = "incomplete"
    KNOWN = "known"
    UNAVAILABLE_OUTSIDE_RETENTION_HORIZON = "unavailable_outside_retention_horizon"

    def __str__(self) -> str:
        return str(self.value)
