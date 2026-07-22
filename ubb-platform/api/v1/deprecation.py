"""Deprecation machinery (ADR-003 §4): the ``Sunset`` header + a registry.

ADR-003 makes the v1 surface additive-only with *deprecate-then-remove*: removing
or renaming anything a client could depend on is allowed, but never silently —
only through a published deprecation. Every deprecation gets, from announcement
day, three things:

* ``deprecated: true`` on the operation in the spec — Ninja's native flag, which
  flows into ``openapi/v1.json``, the docs UI, and the generated SDK;
* a dated changelog entry and an email announcement (process, not code);
* a runtime **``Sunset`` header** (RFC 8594) carrying the shutoff date on every
  response from the deprecated endpoint — the one channel a machine notices.

This module is the last of those: a registry of deprecated routes and the small
middleware that stamps the header. It stands ready **empty** — nothing is
deprecated at launch (see ``api/v1/tests/test_deprecation.py``), so the first
real deprecation is process (append a registry entry + set the spec flag), not
engineering. The minimum notice is 90 days (ADR-003 §4), a floor enforced by
whoever computes the ``sunset`` date, not by this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from django.utils.http import http_date

_PARAM = re.compile(r"\{[^/}]+\}")


def _template_to_regex(path_template: str) -> re.Pattern:
    """Compile an OpenAPI-style path template into an anchored regex.

    ``{param}`` becomes ``[^/]+`` (exactly one path segment — a parameter never
    swallows a subpath or the collection root); everything else is matched
    literally. The template is the same string used as the spec's path key, e.g.
    ``/api/v1/margin/customers/{customer_id}``.
    """
    parts, last = [], 0
    for m in _PARAM.finditer(path_template):
        parts.append(re.escape(path_template[last:m.start()]))
        parts.append(r"[^/]+")
        last = m.end()
    parts.append(re.escape(path_template[last:]))
    return re.compile("".join(parts) + r"\Z")


@dataclass
class DeprecatedRoute:
    """One deprecated operation: the ``(method, path)`` it fires on, the date it
    turns off, and an optional docs link for the ``Sunset`` ``Link`` relation."""

    method: str
    path_template: str
    sunset: date
    link: str | None = None
    _regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self.method = self.method.upper()
        self._regex = _template_to_regex(self.path_template)

    def matches(self, method: str, path: str) -> bool:
        return method.upper() == self.method and self._regex.match(path) is not None

    def sunset_header(self) -> str:
        """The RFC 8594 ``Sunset`` value: an HTTP-date (RFC 7231) at 00:00:00 GMT
        on the shutoff day."""
        midnight = datetime(
            self.sunset.year, self.sunset.month, self.sunset.day, tzinfo=timezone.utc
        )
        return http_date(midnight.timestamp())


# The registry. EMPTY at launch — nothing is deprecated yet. A future deprecation
# appends here (via register_deprecated_route) AND sets deprecated=True on the
# Ninja operation; test_deprecation.py pins the two in lock-step.
DEPRECATED_ROUTES: list[DeprecatedRoute] = []


def register_deprecated_route(
    method: str, path_template: str, sunset: date, link: str | None = None
) -> DeprecatedRoute:
    """Register a route as deprecated. Returns the entry (so a test can pop it).

    The caller must also set ``deprecated=True`` on the matching Ninja operation
    so the spec carries the flag — the consistency test refuses a half-declared
    deprecation.
    """
    route = DeprecatedRoute(method, path_template, sunset, link)
    DEPRECATED_ROUTES.append(route)
    return route


def find_deprecated_route(method: str, path: str) -> DeprecatedRoute | None:
    for route in DEPRECATED_ROUTES:
        if route.matches(method, path):
            return route
    return None


class SunsetHeaderMiddleware:
    """Stamp the RFC 8594 ``Sunset`` header on every response from a deprecated
    route (ADR-003 §4). Scoped to the versioned mount and a no-op while the
    registry is empty (the launch state). Registered in ``config/settings.py``
    outer of the API's response rewriters, so it stamps the final response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/v1/"):
            route = find_deprecated_route(request.method, request.path)
            if route is not None:
                response["Sunset"] = route.sunset_header()
                if route.link:
                    response["Link"] = f'<{route.link}>; rel="sunset"'
        return response
