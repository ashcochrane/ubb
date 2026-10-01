from enum import Enum

class IntegrationBlueprintDiagnosticSeverity(str, Enum):
    ADVISORY = "advisory"
    BLOCKING = "blocking"

    def __str__(self) -> str:
        return str(self.value)
