from enum import Enum

class PricingReceiptProvenanceMarkupRung(str, Enum):
    TENANT_DEFAULT = "tenant_default"

    def __str__(self) -> str:
        return str(self.value)
