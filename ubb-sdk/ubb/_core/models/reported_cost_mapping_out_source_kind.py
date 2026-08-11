from enum import Enum

class ReportedCostMappingOutSourceKind(str, Enum):
    CALLER_SUPPLIED = "caller_supplied"
    CONSTANT = "constant"
    DERIVED = "derived"
    PROVIDER_RESPONSE = "provider_response"

    def __str__(self) -> str:
        return str(self.value)
