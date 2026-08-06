"""What an operation is: a method and a path, named by the contract.

#209, from #155 §8.3. Before this, a hand-written method named its target by
carrying another versioned path string of its own — 81 of them, each an
independent opportunity for the client to disagree with the contract, and the
disagreement invisible until someone called the method against a real server.
Now a method references a constant in :mod:`ubb._operations`, and this is the
type those constants are.

## Why this type exists at all, rather than a plain tuple

`_request(method, path)` is the shape every call site already had, and #209 may
not change it: forty-odd tests in `ubb-sdk/tests/` assert on exactly that pair,
and the ticket's own acceptance criteria require the SDK suite to pass
untouched. So an operation must *become* that pair — which a tuple does — while
also refusing the two mistakes a tuple cannot see:

- **A parameterised route used as though it had no parameters.** Unpacking one
  would send `{customer_id}` to a real server, verbatim. :meth:`__iter__`
  refuses instead.
- **The wrong number of parameters.** An f-string interpolated whatever it was
  given and produced a plausible, wrong path. :meth:`__call__` counts.

Both are refused statically as well, by `tools/sdk_operations` reading this
package's source — so neither reaches a test run. The runtime checks are here
because a rule enforced in one place is a rule with one place to fail, and
because a traceback naming the parameter beats a 404 naming nothing.

## What it deliberately does NOT do

**No escaping.** A value is interpolated with :func:`str`, exactly as the
f-strings it replaces did. Adding percent-encoding here would quietly change
what 39 call sites put on the wire, in a ticket whose whole claim is that
nothing observable changes.

**No transport.** This module imports nothing. It is the vocabulary the shell
uses to name a request, not a thing that makes one.
"""


class Operation:
    """One operation the contract publishes, as a call site names it.

    Two call shapes, and which one applies is decided by the path rather than
    by preference — a route with no parameters cannot take any, and a route
    with parameters cannot go without::

        self._request(*ops.API_V1_TENANT_ENDPOINTS_GET_TENANT_CONFIG)
        self._request(*ops.API_V1_PLAN_ENDPOINTS_UPDATE_PLAN(key), json=body)

    ``operation_id`` is the contract's own identifier, which ADR-0007 §4
    prefers over the method-and-path pair. It is ``None`` for the routes the
    migration ledger excuses: they exist in no spec, so they have no identifier
    to carry, and that absence is the honest record of what they are.
    """

    __slots__ = ("operation_id", "method", "path", "parameters")

    def __init__(self, operation_id, method, path):
        self.operation_id = operation_id
        self.method = method
        self.path = path
        self.parameters = tuple(_parameters(path))

    # -- the two call shapes -------------------------------------------------

    def __iter__(self):
        """``*operation`` -> ``method, path``, for a route with no parameters.

        A parameterised route is refused rather than unpacked. Yielding its
        path would put `{customer_id}` on the wire — a request that reaches a
        real server, gets a 404, and sends whoever reads the log looking for a
        routing bug.
        """
        if self.parameters:
            raise TypeError(
                f"{self._name} takes {self._arity}: call it — "
                f"`*{self._name}({', '.join(self._argument_names)})` — rather "
                f"than unpacking it, which would send its path unfilled.")
        return iter((self.method, self.path))

    def __call__(self, *values):
        """``operation(a, b)`` -> ``(method, path)`` with ``a`` and ``b`` filled.

        Positionally, in the order the path spells them. Positional rather than
        keyword because the ledger's routes have no parameter *names* to key on
        — the ledger records the path with each parameter collapsed to `{}` —
        and one filling rule for every operation is worth more than nicer
        keywords for most of them.
        """
        if len(values) != len(self.parameters):
            raise TypeError(self._arity_message(values))
        return self.method, _fill(self.path, values)

    # -- reading ------------------------------------------------------------

    def __repr__(self):
        return f"<Operation {self.method.upper()} {self.path}>"

    @property
    def _name(self):
        """How to refer to this operation in a message a caller can act on."""
        return self.operation_id or f"{self.method.upper()} {self.path}"

    @property
    def _argument_names(self):
        """Placeholder names for the message, invented where the path has none."""
        return [name or f"arg{index + 1}"
                for index, name in enumerate(self.parameters)]

    @property
    def _arity(self):
        count = len(self.parameters)
        return f"{count} parameter{'' if count == 1 else 's'}"

    def _arity_message(self, values):
        if not self.parameters:
            return (f"{self._name} takes no parameters, and {len(values)} "
                    f"{'was' if len(values) == 1 else 'were'} given. Its path "
                    f"is `{self.path}` — there is nothing in it to fill.")
        return (f"{self._name} takes {self._arity} "
                f"({', '.join(self._argument_names)}), and {len(values)} "
                f"{'was' if len(values) == 1 else 'were'} given. They fill "
                f"`{self.path}` in the order it spells them.")


# ---------------------------------------------------------------------------
# Reading and filling a path template
# ---------------------------------------------------------------------------
#
# Brace depth is tracked rather than matching `{...}` with a regular
# expression, so a parameter whose name itself contained a brace could not end
# a placeholder early and split one position into two. That is the same rule
# `tools/sdk_operations/spec.py` collapses paths by, and the two must agree:
# the gate matches a call to an operation on the collapsed shape, so a path
# this module read as two parameters and that one read as one would resolve
# against the wrong operation.


def _parameters(path):
    """The parameter names in ``path``, in order; ``None`` where unnamed."""
    for name in _placeholders(path):
        yield name or None


def _fill(path, values):
    """``path`` with each placeholder replaced by the next value, as a string."""
    out, depth, taken = [], 0, iter(values)
    for character in path:
        if character == "{":
            depth += 1
            if depth == 1:
                out.append(str(next(taken)))
            continue
        if character == "}":
            if depth:
                depth -= 1
            continue
        if depth == 0:
            out.append(character)
    return "".join(out)


def _placeholders(path):
    """The text inside each top-level ``{...}`` in ``path``, in order."""
    names, depth, current = [], 0, []
    for character in path:
        if character == "{":
            depth += 1
            if depth == 1:
                current = []
                continue
        if character == "}":
            if depth:
                depth -= 1
                if depth == 0:
                    names.append("".join(current))
            continue
        if depth:
            current.append(character)
    return names
