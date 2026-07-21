"""The one error vocabulary (#78, #63): the checked-in code registry.

``openapi/error-codes.json`` — beside the committed spec at the git root — is
the machine contract for every error the API emits. The ``problems`` section
maps each snake_case code to the one status it is served with; the
``verdicts`` section holds the words per-event ingest verdicts, stop fields,
and pre-check refusals draw from (verdicts are data, never problem+json, but
they speak the same vocabulary). Adding a code is compatible; renaming or
removing one is breaking. ``title``/``detail`` are prose, never contractual;
the ``type`` URI derives one-to-one from the code and exists only to link
docs.

``Problem`` is the one exception raised for a coded refusal — products may
raise it (they import ``core``), and the composition layer's central handlers
(``api/v1/problems.py``) render it. An unregistered code is refused at raise
time, so the registry can never silently drift behind the code that speaks
it.
"""
import json
from pathlib import Path
from typing import Optional

from ninja import Schema

# core/problems.py -> the git root (same derivation as api/v1/openapi_export.py)
GIT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = GIT_ROOT / "openapi" / "error-codes.json"

_REGISTRY = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
PROBLEMS = _REGISTRY["problems"]
VERDICTS = _REGISTRY["verdicts"]

# Non-contractual: exists only so `type` can one day resolve to docs.
PROBLEM_TYPE_BASE = "https://ubb.dev/errors/"


class ProblemOut(Schema):
    """RFC 9457 problem+json, for ``response=`` documentation of error
    statuses. Extension members (e.g. ``balance_micros``) are open-world and
    deliberately unmodeled."""

    type: str
    title: str
    status: int
    code: str
    detail: Optional[str] = None


class Problem(Exception):
    """A coded refusal, rendered as RFC 9457 problem+json by the API layer.

    ``extensions`` become top-level members of the rendered body (RFC 9457
    extension members, e.g. ``balance_micros``); ``headers`` are set on the
    response (e.g. ``Retry-After`` on ``rate_limit_exceeded``).
    """

    def __init__(self, code, detail=None, *, extensions=None, headers=None):
        try:
            entry = PROBLEMS[code]
        except KeyError:
            raise ValueError(
                f"unregistered problem code {code!r} — "
                f"add it to openapi/error-codes.json"
            )
        self.code = code
        self.status = entry["status"]
        self.title = entry["title"]
        self.detail = detail
        self.extensions = dict(extensions or {})
        self.headers = dict(headers or {})
        super().__init__(code if detail is None else f"{code}: {detail}")
