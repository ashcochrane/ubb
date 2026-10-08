"""What the renderer's tests ask Python about the files it returned.

The renderer is TypeScript and what it writes is Python, so "the module
compiles", "the conversion is exact" and "the declared name reaches the wire
unchanged" are questions only a Python interpreter can answer. Each command
below answers one, over a directory of files exactly as `render` returned
them, and prints its answer as one JSON document.

Nothing here repairs what it runs. The files are read, compiled, imported and
called as a tenant would; the only things supplied from outside are the two
documented environment variables.

    python harness.py compile       <directory>
    python harness.py facts         <directory>
    python harness.py reported-cost <directory> <cases.json>
    python harness.py response-cost <directory> <cases.json> <function> <representation> <currency>
    python harness.py run           <directory> <script.py>
    python harness.py registry      <concept>...
"""
import ast
import importlib
import io
import json
import os
import sys
import threading
import tokenize
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MODULE = "ubb_integration"

#: A credential that is plainly not one: what a run finds in the environment.
HARNESS_CREDENTIAL = "not-a-real-key"


def _sources(directory):
    root = Path(directory)
    return {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*.py"))}


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------

def compiled(directory):
    """Each Python file, and whether Python accepts it as a program."""
    answers = {}
    for name, source in _sources(directory).items():
        try:
            compile(source, name, "exec")
            answers[name] = None
        except SyntaxError as refused:
            answers[name] = f"{refused.msg} (line {refused.lineno})"
    return answers


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------

def _comments(source):
    return [token.string for token in
            tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT]


def _constants(tree):
    """Every literal constant in a program, but for `...` and `None`."""
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node.value is not Ellipsis and node.value is not None]


def _handlers(tree):
    """Every `except`, with what it catches and the function it sits in."""
    found = []

    def walk(node, function):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if isinstance(node, ast.ExceptHandler):
            found.append({
                "function": function,
                "catches": None if node.type is None else ast.unparse(node.type),
                "reraises": any(isinstance(inner, ast.Raise) and inner.exc is None
                                for inner in ast.walk(node)),
            })
        for child in ast.iter_child_nodes(node):
            walk(child, function)

    walk(tree, None)
    return found


def _functions(tree):
    """Each module-level function: its parameters, and the keywords of every
    call inside it — with the literal a keyword is given, where it is one."""
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        arguments = node.args
        required_keywords = [
            argument.arg
            for argument, default in zip(arguments.kwonlyargs,
                                         arguments.kw_defaults)
            if default is None]
        calls = []
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                calls.append({
                    "callee": ast.unparse(inner.func),
                    "keywords": {
                        keyword.arg: (keyword.value.value
                                      if isinstance(keyword.value, ast.Constant)
                                      else {"expression":
                                            ast.unparse(keyword.value)})
                        for keyword in inner.keywords if keyword.arg},
                })
        found[node.name] = {
            "positional": [argument.arg for argument in
                           arguments.posonlyargs + arguments.args],
            "required_keywords": required_keywords,
            "optional_keywords": [
                argument.arg
                for argument, default in zip(arguments.kwonlyargs,
                                             arguments.kw_defaults)
                if default is not None],
            "has_docstring": ast.get_docstring(node) is not None,
            "calls": calls,
        }
    return found


def facts(directory):
    answers = {}
    for name, source in _sources(directory).items():
        tree = ast.parse(source)
        answers[name] = {
            "comments": _comments(source),
            "constants": [value if isinstance(value, (str, int, bool))
                          else repr(value) for value in _constants(tree)],
            "strings": [value for value in _constants(tree)
                        if isinstance(value, str)],
            "handlers": _handlers(tree),
            "functions": _functions(tree),
            "names": sorted({node.id for node in ast.walk(tree)
                             if isinstance(node, ast.Name)}),
            "imports": sorted(
                {alias.name for node in ast.walk(tree)
                 if isinstance(node, ast.Import) for alias in node.names}
                | {node.module for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom)}),
            "has_module_docstring": ast.get_docstring(tree) is not None,
        }
    return answers


# ---------------------------------------------------------------------------
# reported-cost
# ---------------------------------------------------------------------------

def _load(directory):
    sys.path.insert(0, str(Path(directory).resolve()))
    os.environ.setdefault("UBB_API_KEY", HARNESS_CREDENTIAL)
    return importlib.import_module(MODULE)


def _the_amount(amount):
    """A case's amount as the value it stands for. The platform test that
    writes the cases reads them the same way; the two cannot share a module,
    since this one runs with no platform on its path."""
    kind, text = amount["type"], amount["text"]
    if kind == "decimal":
        return Decimal(text)
    if kind == "integer":
        return int(text)
    if kind == "float":
        return float(text)
    if kind == "boolean":
        return text == "true"
    if kind == "none":
        return None
    assert kind == "string", kind
    return text


def reported_cost(directory, cases_path):
    """The generated conversion and the generated currency rule, run over
    every case the platform answered. Returns the cases that disagree."""
    module = _load(directory)
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    refusals = {module.ReportedCostNotRepresentable: "amount",
                module.ReportedCostCurrencyRefused: "currency"}

    def answered(operation, *arguments):
        try:
            return {"answer": operation(*arguments)}
        except tuple(refusals) as refused:
            return {"refused": refusals[type(refused)]}

    disagreements = []
    for case in cases["amounts"]:
        got = answered(module._to_micros, _the_amount(case["amount"]),
                       case["representation"], case["currency"])
        if got != case["expected"]:
            disagreements.append({"case": case, "got": got})
    for case in cases["currencies"]:
        got = answered(module._pin_currency, case["declared"],
                       case["reported"])
        if got != case["expected"]:
            disagreements.append({"case": case, "got": got})
    return {"amounts": len(cases["amounts"]),
            "currencies": len(cases["currencies"]),
            "disagreements": disagreements}


def read_off_a_response(cases_path, representation, currency):
    """The platform's rows for a cost read off a response that are converted
    as `representation` in `currency`: what one rendered module reads."""
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    return [row for row in cases["read_off_a_response"]
            if (row["representation"], row["currency"]) == (representation,
                                                             currency)]


def response_cost(directory, cases_path, function, representation, currency):
    """A supplier's cost READ OFF A RESPONSE, run through the generated record
    function over every row the platform answered for `representation` in
    `currency` (#583): the response is handed over as Python's `json` reads
    the row's text, the call is answered by a stand-in server, and what it
    sent — or why it refused, having sent nothing — is held to the platform's
    answer. The rows are read from the platform's own file and compared here,
    in Python, because a nineteen-digit answer is not one every reader of
    this one could hold. Returns the rows that disagree."""
    server = Server()
    os.environ["UBB_BASE_URL"] = server.url
    os.environ["UBB_API_KEY"] = HARNESS_CREDENTIAL
    module = _load(directory)
    record = getattr(module, function)
    refusals = {module.ReportedCostNotRepresentable: "amount",
                module.ReportedCostCurrencyRefused: "currency"}
    rows = read_off_a_response(cases_path, representation, currency)
    disagreements = []
    for index, row in enumerate(rows):
        before = len(server.requests)
        try:
            response = json.loads(row["document"])
        except ValueError:
            # The tenant's own parse refuses it, and the module is handed
            # nothing: refused as a response, before anything is sent.
            got = {"refused": "response"}
            if got != row["expected"]:
                disagreements.append({"row": row, "got": got})
            continue
        try:
            record(customer_id="c", idempotency_key=f"e{index}", task_id="t",
                   response=response)
            got = {"answer": server.requests[-1]["body"].get(
                "provider_response_cost_micros")}
            if "provider_cost_micros" in server.requests[-1]["body"]:
                got["on_the_callers_field"] = True
        except tuple(refusals) as refused:
            got = {"refused": refusals[type(refused)]}
            if len(server.requests) != before:
                got["sent"] = True
        if got != row["expected"]:
            disagreements.append({"row": row, "got": got})
    return {"rows": len(rows), "disagreements": disagreements}


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

#: Two things a queued answer may say about the RESPONSE rather than its body:
#: the status it is sent with, and text to send in place of any JSON at all.
HTTP_STATUS = "http_status"
RAW_BODY = "raw_body"


class Server:
    """A local HTTP server standing where UBB would: it keeps every request
    it is sent and answers each with the next body queued for its route, or
    with that route's ordinary answer."""

    def __init__(self):
        self.requests = []
        self.queued = {}
        self._tasks = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw or b"null")
                except ValueError:
                    body = None
                outer.requests.append({
                    "method": "POST", "path": self.path, "body": body,
                    # As it arrived, for what a parsed body cannot show: a
                    # whole number past what a reader's own numbers hold.
                    "raw": raw.decode("utf-8", "replace"),
                    "content_type": self.headers.get("Content-Type"),
                    "authorization": self.headers.get("Authorization")})
                queued = outer.queued.get(self.path) or []
                overrides = dict(queued.pop(0)) if queued else {}
                status = overrides.pop(HTTP_STATUS, 200)
                raw_answer = overrides.pop(RAW_BODY, None)
                answer = (raw_answer.encode() if raw_answer is not None else
                          json.dumps(outer._answer(self.path, body or {},
                                                   overrides)).encode())
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

            def log_message(self, *arguments):
                pass

        self._http = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._http.server_port}"
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

    def queue(self, path, **overrides):
        """The next answer `path` gives carries `overrides`."""
        self.queued.setdefault(path, []).append(overrides)

    def _answer(self, path, body, overrides):
        if path == "/api/v1/tasks":
            self._tasks += 1
            answer = {
                "task_id": f"task_{self._tasks}",
                "parent_task_id": body.get("parent_task_id"),
                "task_type": body.get("task_type"), "status": "active",
                "task_cogs_ceiling_micros": None, "agreed_price_micros": None,
                "external_task_id": "",
                "created_at": "2026-09-02T09:00:00+00:00", "replayed": False}
        elif path == "/api/v1/metering/usage":
            answer = {"event_id": f"event_{len(self.requests)}",
                      "suspended": False, "costing_status": "known",
                      "pricing_status": "known", "stop": False,
                      "task_id": body.get("task_id")}
        elif path.endswith("/close"):
            answer = {
                "task_id": path.split("/")[-2], "parent_task_id": None,
                "status": "completed", "outcome": body.get("outcome"),
                "replayed": False, "charge_created": False,
                "total_billed_cost_micros": 0, "total_provider_cost_micros": 0,
                "unresolved_event_count": 0, "unpriced_event_count": 0,
                "event_count": 0}
        else:
            answer = {}
        answer.update(overrides)
        return answer

    def bodies(self, path):
        return [request["body"] for request in self.requests
                if request["path"] == path]


def run(directory, script_path):
    """Import the rendered module with the two documented variables set, and
    run a test's script against it. The script sets `result`."""
    server = Server()
    os.environ["UBB_BASE_URL"] = server.url
    os.environ["UBB_API_KEY"] = HARNESS_CREDENTIAL
    sys.path.insert(0, str(Path(directory).resolve()))
    scope = {"server": server, "load": lambda: importlib.import_module(MODULE),
             "Decimal": Decimal, "HARNESS_CREDENTIAL": HARNESS_CREDENTIAL,
             "directory": Path(directory).resolve(), "result": None}
    exec(compile(Path(script_path).read_text(encoding="utf-8"),
                 script_path, "exec"), scope)
    return scope["result"]


def registry(*concepts):
    """The values of each closed registry concept asked for, and the version
    of the SDK in this tree — read off the SDK's generated vocabulary, which
    rides its own zero-diff gate against the registry."""
    import ubb
    from ubb import vocabulary
    return {"sdk_version": ubb.__version__,
            "values": {concept: sorted(getattr(vocabulary,
                                               f"{concept.upper()}_VALUES"))
                       for concept in concepts}}


COMMANDS = {"compile": compiled, "facts": facts,
            "reported-cost": reported_cost, "response-cost": response_cost,
            "run": run, "registry": registry}

if __name__ == "__main__":
    answer = COMMANDS[sys.argv[1]](*sys.argv[2:])
    sys.stdout.buffer.write(json.dumps(answer, ensure_ascii=True).encode())
