from enum import Enum

class RecordUsageResponseNotApplicableReasonType0(str, Enum):
    FIXED_TASK_PRICING = "fixed_task_pricing"
    TENANT_NOT_BILLING = "tenant_not_billing"

    def __str__(self) -> str:
        return str(self.value)
