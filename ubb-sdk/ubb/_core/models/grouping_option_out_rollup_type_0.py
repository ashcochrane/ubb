from enum import Enum

class GroupingOptionOutRollupType0(str, Enum):
    EVENT_CATEGORY = "event_category"
    MEASUREMENT_CONCEPT = "measurement_concept"

    def __str__(self) -> str:
        return str(self.value)
