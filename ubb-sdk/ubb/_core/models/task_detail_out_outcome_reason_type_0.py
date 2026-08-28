from enum import Enum

class TaskDetailOutOutcomeReasonType0(str, Enum):
    CUSTOMER_CANCELLED = "customer_cancelled"
    EXECUTION_FAILED = "execution_failed"
    INTERNAL_ERROR = "internal_error"
    INVALID_INPUT = "invalid_input"
    PARENT_CLOSED = "parent_closed"
    SUPERSEDED = "superseded"
    TIMEOUT = "timeout"
    UNSPECIFIED = "unspecified"
    UPSTREAM_PROVIDER_ERROR = "upstream_provider_error"

    def __str__(self) -> str:
        return str(self.value)
