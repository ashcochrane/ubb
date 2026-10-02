from enum import Enum

class IntegrationBlueprintArgumentBindingClass(str, Enum):
    PLATFORM_KNOWN = "platform_known"
    RUNTIME_BOUND = "runtime_bound"
    SECRET_REFERENCE = "secret_reference"

    def __str__(self) -> str:
        return str(self.value)
