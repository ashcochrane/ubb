from enum import Enum

class IntegrationBlueprintDiagnosticObjectKind(str, Enum):
    EVENT_TYPE = "event_type"
    GROUPING_FIELD = "grouping_field"
    MEASUREMENT = "measurement"
    PROVIDER = "provider"
    REPORTED_COST_MAPPING = "reported_cost_mapping"
    SUBTASK_TYPE = "subtask_type"
    TASK_TYPE = "task_type"

    def __str__(self) -> str:
        return str(self.value)
