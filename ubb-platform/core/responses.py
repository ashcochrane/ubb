"""JSON response helper for Router-based handlers.

The single-API restructure (#77) turned the twelve per-mount ``NinjaAPI``
instances into ``Router``s, which have no ``create_response``. This mirrors
``NinjaAPI.create_response`` byte-for-byte for the default JSON renderer —
same encoder, same ``application/json; charset=utf-8`` content type — so
handler call sites only swap the callable name.
"""
from django.http import HttpRequest, HttpResponse
from ninja.renderers import JSONRenderer

_renderer = JSONRenderer()
_content_type = f"{_renderer.media_type}; charset={_renderer.charset}"


def json_response(request: HttpRequest, data, *, status: int) -> HttpResponse:
    content = _renderer.render(request, data, response_status=status)
    return HttpResponse(content, status=status, content_type=_content_type)
