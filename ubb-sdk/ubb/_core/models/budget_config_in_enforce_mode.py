from enum import Enum

class BudgetConfigInEnforceMode(str, Enum):
    ALERT_ONLY = "alert_only"
    BLOCKING = "blocking"

    def __str__(self) -> str:
        return str(self.value)
