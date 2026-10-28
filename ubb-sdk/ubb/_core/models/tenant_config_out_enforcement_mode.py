from enum import Enum

class TenantConfigOutEnforcementMode(str, Enum):
    ENFORCING = "enforcing"
    OFF = "off"

    def __str__(self) -> str:
        return str(self.value)
