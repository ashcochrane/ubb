"""Shared assertion for the one error dialect (#78, #63).

Every error from every route is RFC 9457 ``application/problem+json`` with a
stable snake_case ``code`` from the checked-in registry. ``title``/``detail``
are prose, never contractual — tests assert status, content type, and code.
"""
import json


def assert_problem(response, code, status):
    assert response.status_code == status, (
        response.status_code,
        response.content,
    )
    assert response["Content-Type"] == "application/problem+json", (
        response["Content-Type"]
    )
    body = json.loads(response.content)
    assert body["code"] == code, body
    assert body["status"] == status, body
    return body
