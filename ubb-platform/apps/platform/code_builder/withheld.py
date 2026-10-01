"""The withhold list: what UBB may know and never writes into generated code.

A credential is not unknown and it is not a runtime value. UBB could resolve
it, and deliberately refuses to embed it in a file whose whole purpose is to
be copied and downloaded. That makes withholding a POLICY rather than a
derivation (#156 §6.2, #184 §4): the second of the three questions that assign
a token its binding class is *is it on this list*, and the list is short,
central and named so the decision is reviewable in one place instead of
smeared across whatever builds a call.

**One entry.** A Blueprint describes calls to UBB, and the only credential
those calls carry is the tenant's own API key. The module a Blueprint renders
into never calls the tenant's supplier and emits no webhook handler, so
neither a supplier credential nor a signing secret is a token of any call —
each joins this list on the day a call first carries one.

**The API host is absent on purpose.** It varies between environments, and
that is not what makes something a secret: a generated file reads it from the
environment so one file can be pointed at any server, and there is nothing in
it to leak.

**What each entry carries is a NAME.** The environment variable a generated
file reads the value from, which is the only thing about a withheld value a
Blueprint ever says. No function here takes or returns the value itself.
"""

#: The token every authenticated call carries: the tenant's API key.
API_KEY = "api_key"

#: Withheld token to the environment variable it is read from.
#:
#: ⚠ The variable's spelling is also a symbol of the renderer's catalogue,
#: which pins it by snapshot. It is stated here because the contract's field
#: table puts the variable's name on the Blueprint, and the Blueprint is
#: resolved here; it is not a registry concept (#184 §15).
WITHHELD = {API_KEY: "UBB_API_KEY"}


def is_withheld(token):
    """Whether `token` is one a Blueprint references and never resolves."""
    return token in WITHHELD


def environment_variable(token):
    """The variable a generated file reads `token` from.

    Raises for a token that is not withheld: asking is only meaningful for one
    that is, and an answer of `None` would be a secret reference naming
    nothing.
    """
    return WITHHELD[token]
