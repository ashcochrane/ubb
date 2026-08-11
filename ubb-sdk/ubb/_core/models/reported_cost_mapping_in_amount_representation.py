from enum import Enum

class ReportedCostMappingInAmountRepresentation(str, Enum):
    MAJOR_UNITS_DECIMAL = "major_units_decimal"
    MICROS = "micros"
    MINOR_UNITS = "minor_units"

    def __str__(self) -> str:
        return str(self.value)
