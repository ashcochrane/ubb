from enum import Enum

class MeasurementOutValueType(str, Enum):
    DECIMAL = "decimal"
    INTEGER = "integer"

    def __str__(self) -> str:
        return str(self.value)
