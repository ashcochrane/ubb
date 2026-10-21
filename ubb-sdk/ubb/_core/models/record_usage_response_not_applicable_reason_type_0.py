from enum import Enum

class RecordUsageResponseNotApplicableReasonType0(str, Enum):
    FIXED_TASK_PRICING = "fixed_task_pricing"

    def __str__(self) -> str:
        return str(self.value)
