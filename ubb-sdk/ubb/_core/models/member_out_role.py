from enum import Enum

class MemberOutRole(str, Enum):
    ADMIN = "admin"
    READ = "read"
    WRITE = "write"

    def __str__(self) -> str:
        return str(self.value)
