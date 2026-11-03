"""CI guards over UBB's Stripe call surface (static, AST-walked).

1. **Every production ``stripe_call(`` invocation passes api_key=** (F4.4).
   ``stripe_call``'s api_key parameter is required keyword-only, so a missed
   call site is a TypeError — but only when that code path actually runs. This
   scan turns the omission into a commit-time failure instead: a forgotten
   api_key= is exactly the bug class that silently routed sandbox traffic to
   live Stripe.

2. **No raw ``stripe.<Resource>.<verb>(`` call in production code** (Stage C1a,
   F-2). The wrapper refuses an empty key before any request is built; a raw
   SDK call does not — stripe-python falls back to the global ``stripe.api_key``
   and sends the request. Every outbound call therefore goes through
   ``stripe_call``. The allowlist names the one raw SDK call that verifies a
   signature locally and never reaches transport, plus a ``str`` method on the
   SDK's version string that the dotted-name scan cannot tell apart from a
   call. Module-level ``import stripe``, function-local
   ``import stripe``, ``import stripe as x`` and ``from stripe import X`` are all
   seen.

3. **No ``.get(`` on a name bound from a Stripe object** (Stage C1a, F-3a /
   F-3b). The pinned SDK's ``StripeObject`` is not a dict and has no ``.get``;
   the real-object tests are the authority on runtime shape and this ratchet is
   SUPPLEMENTAL and deliberately narrow — not a data-flow analyser. It follows
   exactly three bindings inside one function body: ``name = <...>.data.object``,
   ``name = stripe_call(...)``, ``name = stripe.<Resource>.<verb>(...)`` — plus
   one step, ``for item in name.auto_paging_iter()`` — and refuses ``.get(`` on
   any attribute chain rooted at such a name, or rooted at ``<...>.data.object``.

Each scanner is proved against a planted negative control, so a scanner that
stopped seeing code fails here rather than passing vacuously.
"""
import ast
from pathlib import Path

import pytest

# apps/billing/stripe/tests/test_*.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[4]

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}

#: Raw SDK calls allowed in production code: exact dotted names.
RAW_CALL_ALLOWLIST = frozenset({
    # Signature verification is local; it never reaches transport.
    "stripe.Webhook.construct_event",
    # The SDK major-version assertion in stripe_service.py (a str method).
    "stripe.VERSION.split",
})

#: ``stripe.error.X`` / ``stripe.oauth_error.X`` are exception classes, not
#: API resources; constructing one is not an outbound call.
_NOT_RESOURCES = frozenset({"error", "oauth_error"})

#: ``.get(`` on a Stripe-bound name allowed in production code — ``file:function``.
GET_ALLOWLIST = frozenset()


def _iter_source_files():
    """Every production .py under apps/, api/, core/ (no tests, no migrations)."""
    for top in ("apps", "api", "core"):
        root = PLATFORM_ROOT / top
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            yield path, rel


def _is_stripe_call(node):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id == "stripe_call"
    if isinstance(f, ast.Attribute):
        return f.attr == "stripe_call"
    return False


# --- 1. stripe_call( passes api_key= -----------------------------------------

def _collect():
    violations, sites = [], 0
    for path, rel in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_stripe_call(node):
                sites += 1
                keywords = {kw.arg for kw in node.keywords}
                # None = a **splat, which may carry api_key — allowed.
                if "api_key" not in keywords and None not in keywords:
                    violations.append(f"{rel.as_posix()}:{node.lineno}")
    return violations, sites


def test_every_stripe_call_invocation_passes_api_key():
    violations, sites = _collect()
    # Guard against a vacuous pass from path-resolution breakage: the codebase
    # has 20+ production stripe_call sites today.
    assert sites >= 20, f"AST walker only found {sites} stripe_call invocations"
    assert not violations, (
        "stripe_call( without api_key= — every call site must pass "
        "api_key=api_key_for_tenant(<tenant in scope>) so sandbox flows can "
        "never silently use the live key:\n" + "\n".join(violations)
    )


# --- 2. no raw stripe.<Resource>.<verb>( -------------------------------------

def _stripe_bindings(tree):
    """Names bound to the stripe module and names imported from it, anywhere
    in the module (function-local imports included)."""
    module_aliases, from_names = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "stripe":
                    module_aliases.add(alias.asname or "stripe")
        elif isinstance(node, ast.ImportFrom) and node.module == "stripe" and node.level == 0:
            for alias in node.names:
                from_names[alias.asname or alias.name] = alias.name
    return module_aliases, from_names


def _dotted(expr):
    """['stripe', 'PaymentIntent', 'retrieve'] for stripe.PaymentIntent.retrieve."""
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    parts.append(expr.id)
    return list(reversed(parts))


def _stripe_api_path(expr, module_aliases, from_names):
    """The normalised ``stripe.X.y`` dotted name if ``expr`` names an SDK
    attribute reached through a stripe binding, else None."""
    parts = _dotted(expr)
    if not parts:
        return None
    root, rest = parts[0], parts[1:]
    if root in module_aliases:
        normalised = ["stripe"] + rest
    elif root in from_names:
        normalised = ["stripe", from_names[root]] + rest
    else:
        return None
    if len(normalised) < 3 or normalised[1] in _NOT_RESOURCES:
        return None
    return ".".join(normalised)


def _raw_calls_in(source, filename="<planted>"):
    """Every raw ``stripe.<Resource>.<verb>(`` call in ``source`` off the
    allowlist, as (lineno, dotted name)."""
    tree = ast.parse(source, filename=filename)
    module_aliases, from_names = _stripe_bindings(tree)
    if not module_aliases and not from_names:
        return [], 0
    found, allowlisted = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _stripe_api_path(node.func, module_aliases, from_names)
        if dotted is None:
            continue
        if dotted in RAW_CALL_ALLOWLIST:
            allowlisted += 1
            continue
        found.append((node.lineno, dotted))
    return found, allowlisted


def _collect_raw_calls():
    violations, files, allowlisted = [], 0, 0
    for path, rel in _iter_source_files():
        files += 1
        found, seen_allowlisted = _raw_calls_in(path.read_text(encoding="utf-8"), str(path))
        allowlisted += seen_allowlisted
        violations += [f"{rel.as_posix()}:{lineno} {dotted}" for lineno, dotted in found]
    return violations, files, allowlisted


def test_no_production_code_calls_the_stripe_sdk_raw():
    violations, files, allowlisted = _collect_raw_calls()
    assert files >= 50, f"AST walker only scanned {files} production files"
    # The ONE receiver core's construct_event (C1b folded the two receivers'
    # copies into `apps/billing/stripe/receiver.py`) plus the wrapper module's
    # VERSION.split are allowlisted hits the scanner must have SEEN — proof it
    # reads real code rather than passing vacuously.
    assert allowlisted >= 2, f"scanner saw only {allowlisted} allowlisted hits"
    assert not violations, (
        "raw stripe.<Resource>.<verb>( call in production code — route it "
        "through stripe_call(stripe.<Resource>.<verb>, api_key=..., ...) so an "
        "empty key is refused before transport (Stage C1a, F-2):\n"
        + "\n".join(violations)
    )


_PLANTED_RAW = {
    "module import": (
        "import stripe\n"
        "def f(acct):\n"
        "    return stripe.Account.retrieve(acct, api_key='')\n",
        "stripe.Account.retrieve"),
    "function-local import": (
        "def f(acct):\n"
        "    import stripe\n"
        "    return stripe.Account.retrieve(acct)\n",
        "stripe.Account.retrieve"),
    "from-import": (
        "from stripe import PaymentIntent\n"
        "def f():\n"
        "    return PaymentIntent.list(limit=1)\n",
        "stripe.PaymentIntent.list"),
    "aliased import": (
        "import stripe as sdk\n"
        "def f():\n"
        "    return sdk.checkout.Session.create()\n",
        "stripe.checkout.Session.create"),
    "oauth token": (
        "import stripe\n"
        "def f(code):\n"
        "    return stripe.OAuth.token(grant_type='authorization_code', code=code)\n",
        "stripe.OAuth.token"),
}


@pytest.mark.parametrize("shape", sorted(_PLANTED_RAW))
def test_the_raw_call_scanner_catches_a_planted_raw_call(shape):
    source, expected = _PLANTED_RAW[shape]
    found, _ = _raw_calls_in(source)
    assert [dotted for _, dotted in found] == [expected]


def test_the_raw_call_scanner_leaves_the_wrapper_and_the_allowlist_alone():
    source = (
        "import stripe\n"
        "from apps.billing.stripe.services.stripe_service import stripe_call\n"
        "def f(payload, sig, secret, key):\n"
        "    event = stripe.Webhook.construct_event(payload, sig, secret)\n"
        "    pi = stripe_call(stripe.PaymentIntent.retrieve, api_key=key, id='pi')\n"
        "    try:\n"
        "        return event, pi\n"
        "    except stripe.error.StripeError:\n"
        "        raise stripe.error.APIError('x')\n"
    )
    found, allowlisted = _raw_calls_in(source)
    assert found == []
    assert allowlisted == 1


# --- 3. no .get( on a Stripe-bound name ---------------------------------------

def _ends_with_data_object(expr):
    """True for an attribute chain ``<...>.data.object`` (an event's payload)."""
    return (isinstance(expr, ast.Attribute) and expr.attr == "object"
            and isinstance(expr.value, ast.Attribute) and expr.value.attr == "data")


def _root_name(expr):
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def _contains_data_object(expr):
    while isinstance(expr, ast.Attribute):
        if _ends_with_data_object(expr):
            return True
        expr = expr.value
    return False


def _binds_a_stripe_object(value, module_aliases, from_names):
    if _ends_with_data_object(value):
        return True
    if isinstance(value, ast.Call):
        if _is_stripe_call(value):
            return True
        return _stripe_api_path(value.func, module_aliases, from_names) is not None
    return False


def _is_auto_paging_of(expr, bound, materialised=False):
    """``name.auto_paging_iter()`` on a bound name — optionally wrapped in
    ``list(...)``, the shape that fetches every page inside a try."""
    if materialised and isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
            and expr.func.id == "list" and len(expr.args) == 1:
        expr = expr.args[0]
    return (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "auto_paging_iter"
            and _root_name(expr.func.value) in bound)


def _stripe_gets_in_function(fn, module_aliases, from_names):
    """(lineno, receiver) for every ``.get(`` on a Stripe-bound name in ``fn``."""
    bound = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and _binds_a_stripe_object(node.value, module_aliases, from_names):
            bound.add(node.targets[0].id)
    # One step: a bound listing's pages, materialised (`listed =
    # list(x.auto_paging_iter())`) or iterated directly, bind each page item.
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and _is_auto_paging_of(node.value, bound, materialised=True):
            bound.add(node.targets[0].id)
    for node in ast.walk(fn):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) \
                and (_is_auto_paging_of(node.iter, bound)
                     or (isinstance(node.iter, ast.Name) and node.iter.id in bound)):
            bound.add(node.target.id)
    found = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get":
            receiver = node.func.value
            if _contains_data_object(receiver) or _root_name(receiver) in bound:
                found.append((node.lineno, ".".join(_dotted(receiver) or ["<expr>"])))
    return found


def _stripe_gets_in(source, filename="<planted>"):
    tree = ast.parse(source, filename=filename)
    module_aliases, from_names = _stripe_bindings(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for lineno, receiver in _stripe_gets_in_function(node, module_aliases, from_names):
                found.append((lineno, node.name, receiver))
    return found


def _collect_stripe_gets():
    violations, files = [], 0
    for path, rel in _iter_source_files():
        files += 1
        for lineno, function, receiver in _stripe_gets_in(path.read_text(encoding="utf-8"), str(path)):
            if f"{rel.as_posix()}:{function}" in GET_ALLOWLIST:
                continue
            violations.append(f"{rel.as_posix()}:{lineno} {function}: {receiver}.get(")
    return violations, files


def test_no_production_code_reads_a_stripe_object_with_get():
    violations, files = _collect_stripe_gets()
    assert files >= 50, f"AST walker only scanned {files} production files"
    assert not violations, (
        "`.get(` on a Stripe SDK object — the pinned StripeObject has no .get; "
        "read it through stripe_service.field / metadata_value (Stage C1a, F-3):\n"
        + "\n".join(violations)
    )


_PLANTED_GET = {
    "event payload": (
        "def h(event):\n"
        "    pi = event.data.object\n"
        "    return pi.metadata.get('topup_attempt_id')\n",
        "pi.metadata"),
    "event payload inline": (
        "def h(event):\n"
        "    return event.data.object.get('id')\n",
        "event.data.object"),
    "wrapper result": (
        "import stripe\n"
        "def g(key):\n"
        "    sub = stripe_call(stripe.Subscription.create, api_key=key)\n"
        "    return sub.get('status', 'active')\n",
        "sub"),
    "raw call result": (
        "import stripe\n"
        "def k():\n"
        "    cust = stripe.Customer.retrieve('cus')\n"
        "    return (cust.get('invoice_settings') or {}).get('default_payment_method')\n",
        "cust"),
    "paged item": (
        "import stripe\n"
        "def p(key):\n"
        "    result = stripe_call(stripe.Invoice.list, api_key=key)\n"
        "    for inv in result.auto_paging_iter():\n"
        "        inv.metadata.get('usage_invoice_id')\n",
        "inv.metadata"),
    "paged item, pages materialised inside a try": (
        "import stripe\n"
        "def p(key):\n"
        "    try:\n"
        "        pis = stripe_call(stripe.PaymentIntent.list, api_key=key)\n"
        "        listed = list(pis.auto_paging_iter())\n"
        "    except Exception:\n"
        "        return\n"
        "    for pi in listed:\n"
        "        pi.metadata.get('topup_attempt_id')\n",
        "pi.metadata"),
}


@pytest.mark.parametrize("shape", sorted(_PLANTED_GET))
def test_the_get_ratchet_catches_a_planted_dict_style_read(shape):
    source, expected_receiver = _PLANTED_GET[shape]
    found = _stripe_gets_in(source)
    assert [receiver for _, _, receiver in found] == [expected_receiver]


def test_the_get_ratchet_ignores_gets_on_names_not_bound_from_stripe():
    source = (
        "import stripe\n"
        "def f(request, event, key):\n"
        "    handler = HANDLERS.get(event.type)\n"
        "    row = Model.objects.get(id=1)\n"
        "    sig = request.META.get('HTTP_STRIPE_SIGNATURE', '')\n"
        "    listing = stripe_call(stripe.Subscription.list, api_key=key)\n"
        "    for sub in listing.auto_paging_iter():\n"
        "        customer_id = customers_by_stripe_id.get(sub.customer)\n"
        "    return handler, row, sig, customer_id\n"
    )
    assert _stripe_gets_in(source) == []
