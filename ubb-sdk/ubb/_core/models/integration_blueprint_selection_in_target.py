from enum import Enum

class IntegrationBlueprintSelectionInTarget(str, Enum):
    PYTHON_SDK = "python_sdk"
    SHELL_HTTP = "shell_http"

    def __str__(self) -> str:
        return str(self.value)
