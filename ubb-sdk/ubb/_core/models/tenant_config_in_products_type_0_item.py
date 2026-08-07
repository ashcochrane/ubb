from enum import Enum

class TenantConfigInProductsType0Item(str, Enum):
    BILLING = "billing"
    METERING = "metering"
    REFERRALS = "referrals"

    def __str__(self) -> str:
        return str(self.value)
