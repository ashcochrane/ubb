from enum import Enum

class EconomicMeasureOutMeasure(str, Enum):
    CUSTOMER_REVENUE = "customer_revenue"
    GROSS_MARGIN = "gross_margin"
    RECORDED_EVENTS = "recorded_events"
    SUPPLIER_COGS = "supplier_cogs"

    def __str__(self) -> str:
        return str(self.value)
