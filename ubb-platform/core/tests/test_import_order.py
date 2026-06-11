"""F3.1 layering smoke-tests.

Verifies:
1. The four names moved to invoice_routing are the same objects re-exported by
   api.v1.webhooks (no shadowing or re-definition).
2. The api→apps import direction is legal (api.v1.webhooks can import the billing
   webhook module, and billing modules can import the routing module) — no
   circular import regardless of which module loads first.
"""
import os
import sys
import subprocess

import django
import pytest


# ── Identity checks (no subprocess needed — same process is fine) ───────────

def test_moved_names_are_same_objects():
    """Names re-exported by api.v1.webhooks must be identical to the originals."""
    import importlib

    routing = importlib.import_module(
        "apps.billing.connectors.stripe.invoice_routing"
    )
    api_wh = importlib.import_module("api.v1.webhooks")

    assert api_wh._invoice_subscription_id is routing._invoice_subscription_id
    assert api_wh._refresh_urls is routing._refresh_urls
    assert api_wh.AR_ALLOWED is routing.AR_ALLOWED
    assert api_wh.ar_transition_allowed is routing.ar_transition_allowed


# ── Import-order independence (fresh interpreter, Django setup) ──────────────

def _django_import_cmd(*module_paths):
    """Return a subprocess argv that imports each module in order."""
    imports = "; ".join(f"import {m}" for m in module_paths)
    return [
        sys.executable, "-c",
        f"import django; django.setup(); {imports}",
    ]


def _run(argv):
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "ubb.settings")
    result = subprocess.run(argv, env=env, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Import failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


def test_api_webhooks_then_billing_webhooks():
    """api.v1.webhooks first, then apps.billing.connectors.stripe.webhooks."""
    _run(_django_import_cmd(
        "api.v1.webhooks",
        "apps.billing.connectors.stripe.webhooks",
    ))


def test_billing_webhooks_then_api_webhooks():
    """apps.billing.connectors.stripe.webhooks first, then api.v1.webhooks."""
    _run(_django_import_cmd(
        "apps.billing.connectors.stripe.webhooks",
        "api.v1.webhooks",
    ))


def test_invoice_routing_importable_standalone():
    """invoice_routing has no circular deps — importable on its own."""
    _run(_django_import_cmd(
        "apps.billing.connectors.stripe.invoice_routing",
    ))


def test_billing_tasks_importable():
    """invoicing/tasks.py no longer lazy-imports api.v1 — clean top-level import."""
    _run(_django_import_cmd(
        "apps.billing.invoicing.tasks",
    ))
