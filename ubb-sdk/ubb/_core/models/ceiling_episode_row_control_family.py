from enum import Enum

class CeilingEpisodeRowControlFamily(str, Enum):
    ADMISSION_CONTROL = "admission_control"
    CEILING = "ceiling"
    CUSTOMER_SPEND_POOL = "customer_spend_pool"
    WALLET_POLICY = "wallet_policy"

    def __str__(self) -> str:
        return str(self.value)
