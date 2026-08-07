from enum import Enum

class TenantConfigOutProductsItem(str, Enum):
    BILLING = "billing"
    METERING = "metering"
    REFERRALS = "referrals"

    def __str__(self) -> str:
        return str(self.value)
