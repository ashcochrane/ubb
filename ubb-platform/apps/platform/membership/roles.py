"""The tenant-principal role vocabulary (identity build 1, #79).

Three roles — no owner tier, no fourth role (ADR authority #62). The same
vocabulary is carried by both tenant-principal schemes: a ``Member``'s role and
a ``TenantApiKey``'s role. This module is pure constants + one comparison helper
so both ``apps.platform.tenants.models`` (the key) and
``apps.platform.membership.models`` (the member) can import it with no risk of a
circular import.

A **role floor** is the minimum role a route requires. ``role_satisfies`` is the
one comparison every floor check goes through: Admin ≥ Write ≥ Read. In this
build only the new identity routes bind a floor (invitations → Admin, members
list → Read); existing tenant routes keep their pre-membership behaviour, and
every ``TenantApiKey`` migrates to Admin, so no existing credential is newly
restricted. Binding floors across the rest of the tenant surface is identity
build 2's job.
"""

ADMIN = "admin"
WRITE = "write"
READ = "read"

ROLE_CHOICES = [
    (ADMIN, "Admin"),
    (WRITE, "Write"),
    (READ, "Read"),
]

# Ascending authority — a role satisfies a floor iff its rank is >= the floor's.
_ROLE_RANK = {READ: 0, WRITE: 1, ADMIN: 2}

VALID_ROLES = frozenset(_ROLE_RANK)


def role_satisfies(role, floor):
    """True if ``role`` meets or exceeds the required ``floor`` role.

    Unknown roles never satisfy any floor (fail closed) — a principal whose
    role is missing or malformed is treated as below every floor.
    """
    if role not in _ROLE_RANK or floor not in _ROLE_RANK:
        return False
    return _ROLE_RANK[role] >= _ROLE_RANK[floor]
