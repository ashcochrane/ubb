from enum import Enum

class CreateGrantRequestKind(str, Enum):
    PAID = "paid"
    PROMO = "promo"

    def __str__(self) -> str:
        return str(self.value)
