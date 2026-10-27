from enum import Enum

class TenantConfigOutTenantPosture(str, Enum):
    FULL_BILLING = "full_billing"
    METERING_ONLY = "metering_only"

    def __str__(self) -> str:
        return str(self.value)
