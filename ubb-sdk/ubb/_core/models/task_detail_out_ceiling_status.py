from enum import Enum

class TaskDetailOutCeilingStatus(str, Enum):
    CEILING_REACHED = "ceiling_reached"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    WITHIN_CEILING = "within_ceiling"

    def __str__(self) -> str:
        return str(self.value)
