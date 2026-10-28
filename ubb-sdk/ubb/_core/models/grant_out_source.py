from enum import Enum

class GrantOutSource(str, Enum):
    API = "api"
    AUTO_TOP_UP = "auto_top_up"
    CHECKOUT = "checkout"
    OTHER = "other"

    def __str__(self) -> str:
        return str(self.value)
