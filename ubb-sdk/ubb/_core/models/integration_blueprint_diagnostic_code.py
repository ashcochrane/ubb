from enum import Enum

class IntegrationBlueprintDiagnosticCode(str, Enum):
    CONSTANT_VALUE_NOT_DECLARED = "constant_value_not_declared"
    DERIVED_MEASUREMENT_UNSUPPORTED = "derived_measurement_unsupported"
    EVENT_TYPE_NOT_DECLARED = "event_type_not_declared"
    EVENT_TYPE_NOT_PUBLISHED = "event_type_not_published"
    EVENT_TYPE_NOT_SELECTED = "event_type_not_selected"
    EVENT_TYPE_REVISED_SINCE_PUBLICATION = "event_type_revised_since_publication"
    REPORTED_COST_MAPPING_MISSING = "reported_cost_mapping_missing"
    REPORTED_COST_PROVIDER_RESPONSE_UNSUPPORTED = "reported_cost_provider_response_unsupported"
    REQUIRED_GROUPING_FIELD_NOT_DECLARED = "required_grouping_field_not_declared"
    REQUIRED_GROUPING_FIELD_RETIRED = "required_grouping_field_retired"
    REQUIRED_GROUPING_FIELD_WRONG_SCOPE = "required_grouping_field_wrong_scope"
    RESPONSE_SHAPE_NOT_DECLARED = "response_shape_not_declared"
    RESPONSE_SHAPE_NOT_READABLE_BY_TARGET = "response_shape_not_readable_by_target"
    SOURCE_PATH_CONVENTION_MISMATCH = "source_path_convention_mismatch"
    TASK_TYPE_NOT_DECLARED = "task_type_not_declared"
    TASK_TYPE_NOT_SELECTED = "task_type_not_selected"
    TASK_TYPE_RETIRED = "task_type_retired"

    def __str__(self) -> str:
        return str(self.value)
