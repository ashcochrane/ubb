from enum import Enum

class TenantConfigInBillingModeType0(str, Enum):
    EXTERNAL = "external"
    POSTPAID = "postpaid"
    PREPAID = "prepaid"

    def __str__(self) -> str:
        return str(self.value)
