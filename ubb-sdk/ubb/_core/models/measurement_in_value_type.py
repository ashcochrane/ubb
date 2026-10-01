from enum import Enum

class MeasurementInValueType(str, Enum):
    DECIMAL = "decimal"
    INTEGER = "integer"

    def __str__(self) -> str:
        return str(self.value)
