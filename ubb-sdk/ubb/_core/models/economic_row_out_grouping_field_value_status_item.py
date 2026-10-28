from enum import Enum

class EconomicRowOutGroupingFieldValueStatusItem(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NOT_RECORDED = "not_recorded"
    RECORDED = "recorded"

    def __str__(self) -> str:
        return str(self.value)
