from enum import Enum

class TenantConfigInEnforcementModeType0(str, Enum):
    ENFORCING = "enforcing"
    OFF = "off"

    def __str__(self) -> str:
        return str(self.value)
