"""Which generated names a consumer holds by reference.

This is the half of the census that #191 decision 3 exists to shape. Scanning a
consumer's source for string literals that match the registry's values is a
check a coincidence can satisfy — two unrelated places spelling the same word
pass it, and a value that moved passes it too, because the old spelling is still
a string. So nothing here reads a value. It reads **names**: the identifiers the
generator binds, asked of the generator rather than re-derived, and found by the
one structure that cannot be a coincidence — an import.

Two languages, because there are two languages. Python covers the backend and
the SDK; TypeScript covers the console. Both answer the same question and return
the same shape, so :mod:`tools.consumers.census` has one predicate rather than
one per surface.

**An import shape that hides the answer is a fault, not a pass.** `from x import
*` puts every name in scope, so a reader cannot tell which values a consumer
actually holds — and treating it as "holds everything" would let one line excuse
a whole surface. It is reported, and no artifact in this repository uses it: the
SDK's generated module says outright that it is not star-exported, for the
adjacent reason that a re-export list is the second copy the artifact abolishes.
"""

import ast
import json
import re

from . import errors as codes
from .errors import CensusError

#: What a TypeScript import statement looks like, in the two forms that reach a
#: generated artifact. Deliberately not a parser: the contract suite pins itself
#: to pytest and PyYAML (`tests/contracts/requirements.txt`), and adding a
#: TypeScript toolchain to answer "which names does this file import" would cost
#: more than the question is worth. The shapes below are ES module syntax, which
#: is fixed, and anything they do not match is invisible rather than guessed at
#: — which is why the console also carries the star-import fault.
_TS_NAMED_IMPORT = re.compile(
    r'import\s+(?:type\s+)?\{(?P<names>[^}]*)\}\s*from\s*["\'](?P<from>[^"\']+)["\']',
    re.S)
_TS_NAMESPACE_IMPORT = re.compile(
    r'import\s+\*\s+as\s+(?P<alias>\w+)\s+from\s*["\'](?P<from>[^"\']+)["\']')
#: One clause of a named import: `A`, `A as B`, `type A`, `type A as B`. The
#: name that matters is the FIRST one — what the artifact calls it — because
#: that is the identifier the generator bound. What the consumer renames it to
#: locally is its own business.
_TS_CLAUSE = re.compile(r'^\s*(?:type\s+)?(?P<name>\w+)(?:\s+as\s+\w+)?\s*$')


def python_references(text, module, location):
    """``(names, faults)`` — what this Python source imports from ``module``.

    Three shapes reach a generated module, and all three are real in this tree:

        from core.vocabulary import TASK_STATUS_ACTIVE      -> {TASK_STATUS_ACTIVE}
        from core import vocabulary; vocabulary.TASK_STATUS_ACTIVE
        import core.vocabulary as v; v.TASK_STATUS_ACTIVE

    A relative import resolves against ``module``'s own package, so the SDK's
    ``from .vocabulary import X`` — the spelling a module inside ``ubb/`` would
    use — is read as ``ubb.vocabulary`` rather than missed.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return frozenset(), (CensusError(
            codes.CONSUMER_UNPARSEABLE, location,
            f"is not parseable Python: {exc}"),)

    package, _, leaf = module.rpartition(".")
    names, aliases, faults = set(), set(), []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = _resolved(node, package)
            if resolved == package:
                # `from ubb import vocabulary` — the spelling the SDK's own
                # docstring recommends. It binds the MODULE, so the names it
                # reaches are attribute accesses, not this statement's list.
                aliases |= {alias.asname or alias.name for alias in node.names
                            if alias.name == leaf}
                continue
            if resolved != module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    faults.append(CensusError(
                        codes.STAR_IMPORT, location,
                        f"`from {module} import *` puts every generated name in "
                        f"scope without saying which values this consumer "
                        f"holds. Import the names you use."))
                else:
                    names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    # `import core.vocabulary` binds `core`; `... as v` binds
                    # `v`. Only the second reaches the module by one name, and
                    # the first is read through the attribute walk below.
                    aliases.add(alias.asname or alias.name)

    if aliases:
        names |= _attributes_of(tree, aliases)
    return frozenset(names), tuple(faults)


def typescript_references(text, specifiers, location):
    """``(names, faults)`` — what this TypeScript source imports from the
    artifact, given every module specifier that resolves to it.

    The specifiers are computed once by the caller, from the console's own
    declared path alias and from this file's position, so the resolution rule
    lives beside the tsconfig it comes from rather than inside the matcher.
    """
    names, faults = set(), []

    for match in _TS_NAMED_IMPORT.finditer(text):
        if match.group("from") not in specifiers:
            continue
        for clause in match.group("names").split(","):
            if not clause.strip():
                continue
            found = _TS_CLAUSE.match(clause)
            if found:
                names.add(found.group("name"))

    for match in _TS_NAMESPACE_IMPORT.finditer(text):
        if match.group("from") not in specifiers:
            continue
        alias = match.group("alias")
        names |= set(re.findall(rf'\b{re.escape(alias)}\.(\w+)', text))

    if re.search(r'export\s+\*\s+from\s*["\'](?:'
                 + "|".join(re.escape(s) for s in specifiers) + r')["\']', text):
        faults.append(CensusError(
            codes.STAR_IMPORT, location,
            "`export * from` the generated artifact re-exports every name "
            "without saying which values this consumer holds. Import the names "
            "you use."))

    return frozenset(names), tuple(faults)


def console_specifiers(source_path, artifact_path, alias_roots):
    """Every module specifier ``source_path`` could import the artifact by.

    Two of them, and both are in use in this console: the declared path alias
    (`@/lib/vocabulary`) and a relative path from the importing file
    (`./vocabulary`). Extensions are stripped because TypeScript resolves
    without them and nothing in this tree writes one.
    """
    stem = _drop_extension(artifact_path)
    specifiers = set()

    for pattern, roots in alias_roots.items():
        prefix = pattern.removesuffix("*")
        for root in roots:
            if stem.startswith(root):
                specifiers.add(prefix + stem[len(root):])

    here = source_path.rpartition("/")[0].split("/")
    there = stem.split("/")
    common = 0
    while (common < min(len(here), len(there) - 1)
           and here[common] == there[common]):
        common += 1
    upwards = len(here) - common
    relative = "/".join([".."] * upwards + there[common:])
    specifiers.add(relative if upwards else "./" + relative)
    return frozenset(specifiers)


def console_alias_roots(tsconfig_text, location):
    """``({alias pattern: (repository-relative root, ...)}, faults)``.

    Read from the console's own `tsconfig.json` rather than pinned here. The
    alias is the console's declaration of where its modules live; a second copy
    in this file would be one more thing to keep true, and it would go stale
    silently — the census would simply stop seeing aliased imports and report a
    surface that imports nothing as a surface that holds nothing.
    """
    try:
        document = json.loads(tsconfig_text)
    except ValueError as exc:
        return {}, (CensusError(
            codes.ALIAS_UNRESOLVED, location,
            f"does not parse as JSON, so the console's path aliases cannot be "
            f"resolved and an aliased import would be invisible: {exc}"),)

    options = document.get("compilerOptions")
    paths = options.get("paths") if isinstance(options, dict) else None
    if not isinstance(paths, dict) or not paths:
        return {}, (CensusError(
            codes.ALIAS_UNRESOLVED, location,
            "declares no `compilerOptions.paths`. The console imports the "
            "generated artifact by alias, so without them the census would "
            "read a served consumer as an empty one."),)
    return paths, ()


def resolve_alias_roots(paths, base):
    """The declared aliases as repository-relative roots.

    ``base`` is the directory `tsconfig.json` sits in — the surface's root —
    because `baseUrl` and every target in `paths` are relative to it.
    """
    resolved = {}
    for pattern, targets in paths.items():
        if not isinstance(targets, list):
            continue
        roots = tuple(f"{base}/{str(target).removeprefix('./').removesuffix('*')}"
                      for target in targets if isinstance(target, str))
        if roots:
            resolved[pattern] = roots
    return resolved


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _resolved(node, package):
    """An ``ImportFrom``'s absolute module name, resolving a relative one.

    ``from . import x`` has no module at all, which is why ``node.module`` is
    joined rather than assumed. One level of ``.`` means "this package", so the
    first level consumes nothing — the same rule Python itself applies.
    """
    if not node.level:
        return node.module or ""
    parts = package.split(".") if package else []
    climb = node.level - 1
    base = parts[:len(parts) - climb] if climb else parts
    return ".".join([*base, node.module] if node.module else base)


def _attributes_of(tree, aliases):
    """Every ``alias.NAME`` in the source, for a namespace import.

    Dotted aliases (`import core.vocabulary` binds `core`) are matched on the
    attribute chain, so `core.vocabulary.TASK_STATUS_ACTIVE` is read correctly
    rather than yielding `vocabulary`.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _chain(node.value) in aliases:
            found.add(node.attr)
    return found


def _chain(node):
    """``a.b.c`` as a dotted string, or ``None`` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _chain(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _drop_extension(path):
    return re.sub(r"\.(ts|tsx|d\.ts)$", "", path)
