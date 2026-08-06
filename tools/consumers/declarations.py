"""Where a consumer keeps its own enumeration, so a debt names a line.

#227 names the three shapes an enumeration takes in this tree: Django
``choices=`` lists, TypeScript unions of string literals, and SDK
``Literal[...]`` annotations. This module finds them.

**They are evidence, not findings.** A finding is the absence of a reference,
established in :mod:`tools.consumers.census` without reading a value; what this
module adds is *where the consumer restates instead*, so a ledger entry can name
`models.py:107` rather than `models.py`. It never runs the other way round.

The reason is worth stating, because the inverse looks reasonable until it is
tried. To report a bare enumeration as a violation, the census would have to
decide **which concept it enumerates** — and the only mechanical way to do that
is to compare its members against a registry value set, which is precisely the
literal scan #191 decision 3 rules out. An enumeration no concept declares a
consumer for is therefore invisible here, deliberately. What covers it is a
concept being declared for it (#191 story 15) — not this gate guessing.

So the function below is allowed to be approximate in a way the census is not.
A shape it misses costs a line number in a reason; a shape it invents does the
same. Neither can turn a gate red or green.
"""

import ast
import re
from dataclasses import dataclass

#: A TypeScript enumeration, in the two spellings the console uses: an
#: `as const` array of string literals, and a union type over them.
_TS_AS_CONST = re.compile(
    r'(?:export\s+)?const\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*\[[^\]]*?"[^"]*"'
    r'[^\]]*\]\s*as\s+const', re.S)
_TS_UNION = re.compile(
    r'(?:export\s+)?type\s+(?P<name>\w+)\s*=\s*"[^"]*"\s*\|')


@dataclass(frozen=True)
class Restatement:
    """One enumeration a consumer holds itself."""
    line: int
    label: str

    def __str__(self):
        return f"line {self.line}: {self.label}"


#
# One reader per surface, named rather than selected by sniffing a path. Each
# is what `census.SURFACES` holds for its surface, so a surface's language is
# declared in one place instead of being re-derived wherever it is needed.
#

def django_choices(text):
    """The backend's shape: every ``choices=`` argument, located."""
    return _python(text, _choices_arguments)


def literal_annotations(text):
    """The SDK's shape: every ``Literal[...]`` annotation, located."""
    return _python(text, _literals)


def typescript_enumerations(text):
    """The console's shape: `as const` arrays and string-literal unions."""
    found = []
    for pattern, shape in ((_TS_AS_CONST, "as const"), (_TS_UNION, "union")):
        for match in pattern.finditer(text):
            found.append(Restatement(text[:match.start()].count("\n") + 1,
                                     f"{match.group('name')} ({shape})"))
    return tuple(sorted(found, key=lambda r: r.line))


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def _python(text, find):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # The census already reported this file as unparseable, with a code.
        # Saying it twice in a reason nobody can act on helps nobody.
        return ()
    return tuple(sorted(find(tree), key=lambda r: r.line))


def _choices_arguments(tree):
    """Every ``choices=`` argument, resolved through a module-level name.

    `choices=TASK_STATUS_CHOICES` is the common spelling, so reporting the
    keyword's own line would point at the model field and not at the list a
    reader has to change. Where the name resolves, the list is what gets named.
    """
    assigned = {target.id: node.value
                for node in tree.body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "choices":
                continue
            value = keyword.value
            if isinstance(value, ast.Name) and value.id in assigned:
                yield Restatement(assigned[value.id].lineno,
                                  f"choices={value.id}")
            else:
                yield Restatement(value.lineno, "choices=")


def _literals(tree):
    """Every ``Literal[...]`` — the SDK's spelling of a closed value set."""
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript)
                and _name_of(node.value) == "Literal"):
            yield Restatement(node.lineno, "Literal[...]")


def _name_of(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
