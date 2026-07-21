"""Offline rendering of the committed OpenAPI document (#77, ADR-002).

The one authority for (a) where the committed document lives and (b) the
canonical serialization. The exporter script, CI's drift gate, and the
in-suite drift pin all render through here, so the bytes cannot disagree
by construction.
"""
import json
from pathlib import Path

# ubb-platform/api/v1/openapi_export.py -> the git root
GIT_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_SPEC_PATH = GIT_ROOT / "openapi" / "v1.json"


def generated_document_text() -> str:
    """The composed API's OpenAPI document, rendered deterministically:
    sorted keys, 2-space indent, trailing newline (LF — writers must pass
    ``newline="\\n"``). Requires Django to be set up."""
    from api.v1.api import api

    schema = api.get_openapi_schema()
    _refuse_duplicate_operation_ids(schema)
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _refuse_duplicate_operation_ids(schema) -> None:
    """A duplicate operationId (two same-named view functions in one module)
    would silently corrupt the document for generators — refuse loudly."""
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    duplicates = sorted(
        {op_id for op_id in operation_ids if operation_ids.count(op_id) > 1}
    )
    if duplicates:
        raise ValueError(
            f"duplicate operationIds in the generated document: {duplicates}"
        )
