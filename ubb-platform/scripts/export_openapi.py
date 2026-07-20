"""Generate ``openapi/v1.json`` (git root) offline from the composed API.

The committed document is the single source of truth for the tenant surface
(ADR-002); CI's drift gate re-runs this script and fails on any diff, so a
surface change that skips regeneration — or a hand edit to the document —
turns CI red. Rendering and target path live in ``api.v1.openapi_export``,
shared with the in-suite drift pin. Run from ``ubb-platform/``::

    python scripts/export_openapi.py
"""
import json
import os
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()


def main() -> None:
    from api.v1.openapi_export import COMMITTED_SPEC_PATH, generated_document_text

    document = generated_document_text()
    COMMITTED_SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": committed bytes must not depend on the generating OS.
    COMMITTED_SPEC_PATH.write_text(document, encoding="utf-8", newline="\n")

    schema = json.loads(document)
    print(
        f"wrote {COMMITTED_SPEC_PATH}: "
        f"{len(schema['paths'])} paths, "
        f"{len(schema.get('webhooks', {}))} webhook event types"
    )


if __name__ == "__main__":
    main()
