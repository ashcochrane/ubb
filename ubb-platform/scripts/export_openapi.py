"""Generate ``openapi/v1.json`` (git root) offline from the composed API.

The committed document is the single source of truth for the tenant surface
(ADR-002); CI's drift gate re-runs this script and fails on any diff, so a
surface change that skips regeneration — or a hand edit to the document —
turns CI red.

Deterministic output: sorted keys, 2-space indent, LF newlines, trailing
newline. Run from ``ubb-platform/``::

    python scripts/export_openapi.py
"""
import json
import os
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
GIT_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(PLATFORM_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()


def main() -> None:
    from api.v1.api import api

    # No explicit path_prefix: let ninja resolve the mount root ("/api/v1/")
    # from the URLconf, exactly as the runtime /api/v1/openapi.json does —
    # offline and runtime documents stay identical by construction.
    schema = api.get_openapi_schema()

    # A duplicate operationId (two same-named view functions in one module)
    # would silently corrupt the document for generators — refuse loudly.
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
        sys.exit(f"duplicate operationIds in the generated document: {duplicates}")

    target = GIT_ROOT / "openapi" / "v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    document = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    # newline="\n": committed bytes must not depend on the generating OS.
    target.write_text(document, encoding="utf-8", newline="\n")
    print(
        f"wrote {target.relative_to(GIT_ROOT)}: "
        f"{len(schema['paths'])} paths, "
        f"{len(schema.get('webhooks', {}))} webhook event types"
    )


if __name__ == "__main__":
    main()
