"""Schemathesis conformance sweep (#87) — wanted, not gating.

Fuzzes the composed API in-process (WSGI) against the committed
``openapi/v1.json`` and reports every place the implementation contradicts
the document: undocumented status codes, response-shape mismatches, and
violations of the error dialect's problem+json envelope
(``docs/conventions/api-contract.md``).

Excluded from the default suite (``norecursedirs`` in ``pytest.ini``) so the
main run never needs schemathesis installed and findings never gate a PR.
Run explicitly, from ``ubb-platform/`` with schemathesis installed::

    pip install "schemathesis==4.24.2"
    python -m pytest conformance -q

CI runs the same command as the non-blocking ``conformance`` job: the step
reports into the job summary and uploads its log, but never turns a PR red.
Promoting it to a gate is a separate future decision (#87).
"""
