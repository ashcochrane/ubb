"""UUID-backed identifiers, validated at the router boundary (#102).

Model primary keys are UUIDs (``core/models.BaseModel``), but the committed
v1 document types their identifiers as bare strings — so a non-UUID value
like ``"0"`` is doc-legal input that used to blow up inside the ORM lookup
(django ``ValidationError`` → 500 ``internal_error``). ``UUIDIdentifier``
refuses it at the boundary instead: the value must parse as a UUID but
passes through unchanged as ``str``, and — deliberately — renders in the
OpenAPI document exactly as a plain ``string`` (``AfterValidator`` adds no
JSON-schema facet), so the committed contract's identifier typing does not
move (typing them ``format: uuid`` narrows the documented input space — a
contract change under ADR-003, and a separate maintainer decision).

Lives in ``core`` — the shared kernel — because product API modules
(``apps/*/api``) annotate their own identifier params and may never import
``api.*`` (ADR-001); the composition layer and products both reach it here,
exactly like ``core/problems.py``.

The central validation handler (``api/v1/problems.py``) maps the failure by
channel: a path identifier that cannot parse cannot name a resource, so it
answers the same bare 404 as a nonexistent one; query and body failures
stay 422 validation problems. ``loc``'s first element carries the channel;
the error ``type`` below is the marker the handler matches on.
"""
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

# The pydantic error `type` of a refused identifier — problems.py matches
# on it to pick the 404 lane for path-channel failures.
UUID_IDENTIFIER_ERROR = "uuid_identifier"


def _validate(value: str) -> str:
    try:
        # The same parse the ORM's UUIDField would attempt at lookup time,
        # so a value that passes here can never blow up down there.
        UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise PydanticCustomError(
            UUID_IDENTIFIER_ERROR, "value is not a valid UUID identifier"
        )
    return value


UUIDIdentifier = Annotated[str, AfterValidator(_validate)]


def is_path_identifier_error(error) -> bool:
    """True when a pydantic error dict is a refused *path* identifier."""
    loc = error.get("loc") or ()
    return (
        error.get("type") == UUID_IDENTIFIER_ERROR
        and len(loc) > 0
        and loc[0] == "path"
    )
