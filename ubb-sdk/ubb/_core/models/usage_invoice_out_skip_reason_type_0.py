from enum import Enum

class UsageInvoiceOutSkipReasonType0(str, Enum):
    NOTHING_TO_BILL = "nothing_to_bill"
    NOT_CHARGE_READY = "not_charge_ready"
    NO_STRIPE_CUSTOMER = "no_stripe_customer"
    NO_USAGE = "no_usage"
    PAYMENT_RAIL_CLOSED = "payment_rail_closed"
    SEAT_SUPERSEDED = "seat_superseded"

    def __str__(self) -> str:
        return str(self.value)
