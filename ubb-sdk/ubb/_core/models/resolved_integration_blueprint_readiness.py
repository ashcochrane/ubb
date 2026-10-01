from enum import Enum

class ResolvedIntegrationBlueprintReadiness(str, Enum):
    BLOCKED = "blocked"
    COMPLETE = "complete"
    SCAFFOLD = "scaffold"

    def __str__(self) -> str:
        return str(self.value)
