"""Render the registry into the artifacts its consumers import.

ADR-0008 §3: **a canonical token is authored once; every other appearance is
generated or verified.** This module is the "generated" half. It turns a
compiled :class:`~tools.vocabulary.compiler.Registry` into source files that
consumers *import*, so a backend model, a console module or an SDK client holds
a canonical value by reference rather than restating the string.

That is what makes the check unfoolable. Scanning source for matching string
literals would pass whenever two unrelated places happened to spell the same
word; importing means the two cannot disagree at all, because there is only one
of them.

A target is anything carrying ``path`` and ``render(registry)``. Issue #200
shipped the first — the backend constants; #207 added the console value lists
and the SDK constants, in the two other languages; the OpenAPI known-value
metadata (#208) is a new entry in :data:`TARGETS` and inherits the zero-diff
gate, the ``--write`` command and the CLI's report without touching this
contract.

Four rules hold for every target, and all four are tested:

- **Deterministic.** Same registry, same bytes, on any machine and in any
  order. A zero-diff gate over an unstable renderer fails at random, and a gate
  that cries wolf gets disabled rather than obeyed.
- **Refusal over a plausible-looking lie.** Where the registry is valid but
  cannot be rendered honestly — two concepts whose constants would collide on
  one name — generation raises :class:`GenerationFailed`. Silently emitting the
  name once, or twice with the second winning, is not a diff anybody notices.
- **The kind decides what is emitted.** A `closed` concept emits its complete
  value list, an `open` one emits its known values and records that unknown
  values stay legal, and a `tenant_defined` one emits no value list at all —
  map #137 constraint 5, which is why no generator may enumerate what the
  tenant owns.
- **No user-facing English.** Every string a target emits is a registry token
  or a label key. Prose appears only in comments, because ADR-0008 §4 draws the
  line at the point vocabulary becomes copy: a vocabulary artifact that carries
  the wording either turns into an i18n database or privileges English inside
  the domain model.
"""

import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

#: Comment and code lines wrap here. The marker plus its trailing space is
#: subtracted per target, so `# ` and `// ` both land the widest comment line on
#: 79, which is where the rest of the repository sits.
_RULE_WIDTH = 79

#: A decision rule renders as three nested levels — the input assignment, the
#: value it answers, and why. Each sits one step in from the last, so a reader
#: scanning for "what happens when X" can stop at the middle one.
_RULE_INDENT = 2
_ANSWER_INDENT = 4
_REASON_INDENT = 7

#: A comment block is a list of ``(indent, text)``. ``_BREAK`` is a bare marker
#: line — the separator that keeps a wrapped paragraph from running into the
#: next one.
#:
#: A distinct object rather than ``None`` or ``""``, because both of those are
#: what a registry field that lost its content looks like: a summary that came
#: back empty would silently render as a separator instead of failing. Same
#: reasoning as ``tests/contracts/_helpers.py``'s ``ABSENT``.
_BREAK = object()


class GenerationFailed(Exception):
    """The registry is valid, but an artifact cannot be rendered honestly.

    Distinct from
    :class:`~tools.vocabulary.errors.RegistryInvalid` on purpose: the registry
    passed every rule it declares, and the fault is in what one particular
    surface can faithfully express. A Python constants module cannot give two
    concepts one name; a different surface with different naming rules might
    have no such problem, and should not be told the registry is broken.
    """


_NO_CONSTANTS_NOTE = (
    "No constants: this kind declares no values by construction. The section "
    "is here so that fact is visible, rather than looking like a concept the "
    "generator lost."
)


# ---------------------------------------------------------------------------
# What every target shares
# ---------------------------------------------------------------------------

class _Target:
    """One generated artifact.

    Subclasses supply the language: the comment marker, the banner, and how a
    concept's values become source. What lives here is everything that must be
    the same across languages — the section order, the commentary each section
    carries, and the refusal to emit a namespace two concepts collide in.
    """

    #: Repository-relative path of the committed artifact.
    path = ""
    #: The line comment marker for this language.
    marker = ""

    # --- the whole artifact --------------------------------------------------

    def render(self, registry):
        """The artifact's full source text, for this registry."""
        self._check_for_collisions(registry)
        sections = [self._section(concept, registry)
                    for _, concept in sorted(registry.concepts.items())]
        return self._preamble() + "\n" + "\n\n".join(sections)

    def _preamble(self):
        raise NotImplementedError

    def _section(self, concept, registry):
        """One concept: its commentary, then whatever its kind emits."""
        lines = self._heading(concept, registry)
        body = self._body(concept)
        if not body:
            return "\n".join(lines + self._comment(
                [(0, _BREAK), (0, _NO_CONSTANTS_NOTE)])) + "\n"
        return "\n".join(lines + [""] + body) + "\n"

    def _body(self, concept):
        """The concept's values as source, or ``[]`` where it declares none."""
        raise NotImplementedError

    # --- the commentary every language carries -------------------------------

    def _heading(self, concept, registry):
        """The section rule and the concept's own account of itself.

        Identical across languages by construction rather than by convention:
        a reader who knows the backend module can read the console one, and a
        summary reworded in the registry moves in all of them at once.
        """
        rule = registry.schema.kinds[concept.kind]
        blocks = [
            (0, _BREAK),
            (0, f"{concept.kind} — {rule.summary.strip()}"),
            (0, _BREAK),
            (0, concept.summary.strip()),
            (0, _BREAK),
            (0, f"Declared in {concept.source}."),
        ]
        blocks += _decision_rule_blocks(concept)
        return [self._section_rule(concept.name)] + self._comment(blocks)

    def _section_rule(self, name):
        """`<marker> --- name ---...` padded to the repository's line width."""
        prefix = f"{self.marker} --- {name} "
        return prefix + "-" * max(3, _RULE_WIDTH - len(prefix))

    def set_name(self, concept):
        """The name the concept's whole declared set is bound to.

        The suffix follows the field the registry populated, which IS the kind
        distinction expressed as data: `closed` requires `values`, `open`
        requires `known_values`. It lives here rather than in each language
        because it is the same rule in all of them, and it is the rule that
        stops `x not in <CONCEPT>_VALUES` reading as "reject it" for a concept
        where rejecting an unseen value is exactly what ADR-0003 forbids.
        """
        suffix = "known_values" if concept.known_values else "values"
        return _identifier(f"{concept.name}_{suffix}")

    def handles(self, concept):
        """``{generated name: the values a consumer referencing it holds}``.

        The inverse of rendering, and it lives here for the reason rendering
        does: a target is the authority on what it binds, so the question
        *"which names carry this concept's values?"* has one answer rather than
        one per caller. The consumer census (#227) reads it to decide whether a
        declared consumer holds a value BY REFERENCE, which is what makes that
        check structural rather than a comparison of spellings; #208 reads the
        same answer through the census's predicate.

        A concept that declares no values binds nothing and yields nothing —
        `tenant_defined` and `free_text`, which is map #137 constraint 5 and
        not an omission.
        """
        if not concept.declared_values:
            return {}
        return {self.set_name(concept): frozenset(concept.declared_values)}

    def _comment(self, blocks):
        """``(indent, text)`` blocks as comment lines in this language."""
        width = _RULE_WIDTH - len(self.marker) - 1
        lines = []
        for indent, text in blocks:
            if text is _BREAK:
                lines.append(self.marker)
                continue
            pad = " " * indent
            wrapped = textwrap.wrap(" ".join(text.split()), width=width - indent,
                                    break_long_words=False,
                                    break_on_hyphens=False)
            lines += [f"{self.marker} {pad}{line}" for line in wrapped] \
                or [self.marker]
        return lines

    # --- refusing a namespace two concepts collide in ------------------------

    def _claims(self, concept):
        """``(name, what it is)`` for everything this concept binds.

        Every target declares what it claims and the shared checker refuses a
        duplicate. A collision is a fault of the *surface*, not the registry —
        which is why it cannot be checked once in the compiler.
        """
        raise NotImplementedError

    def _check_for_collisions(self, registry):
        """Refuse a registry two concepts cannot share a namespace in.

        `billing_mode`/`is_x` and `billing`/`mode_is_x` both want
        `BILLING_MODE_IS_X`. Emitting it once gives one concept the other's
        value; emitting it twice lets the later assignment win silently. Both
        are wrong in a way no reviewer would catch in a generated diff.
        """
        claimed = {}
        collisions = []
        for _, concept in sorted(registry.concepts.items()):
            for name, described in self._claims(concept):
                if name in claimed:
                    collisions.append(f"{name} is the name for both "
                                      f"{claimed[name]} and {described}")
                else:
                    claimed[name] = described
        if collisions:
            raise GenerationFailed(
                f"{self.path} cannot be rendered — one name cannot carry two "
                f"values:\n" + "\n".join(f"  {line}" for line in collisions)
            )


# ---------------------------------------------------------------------------
# The Python constants modules — the backend's, and the SDK's
# ---------------------------------------------------------------------------

class _PythonConstants(_Target):
    """A flat module of literals, for a Python consumer.

    One module rather than a package with a hand-written ``__init__``
    re-exporting a private ``_generated``: the re-export layer would be a
    second, hand-maintained copy of every name — precisely the thing this
    artifact exists to abolish. What keeps a hand edit out is the banner, the
    LF pin in ``.gitattributes`` and the zero-diff gate, which is the same
    arrangement the SDK's generated exception hierarchy already lives under.

    Two consumers share this renderer because the artifact is the same artifact:
    the platform and the SDK are separately installable and cannot import each
    other, so each needs its own copy — but a copy that is *generated* is what
    ADR-0008 §3 sanctions, and a second renderer is what it forbids.
    """

    marker = "#"
    #: The module docstring — the one thing that genuinely differs, because the
    #: two consumers hold these values for different reasons.
    docstring = ""

    def _preamble(self):
        return (f"{self.marker} @generated from domain-vocabulary/ — do not "
                f"edit by hand.\n"
                f"{self.marker} Regenerate with "
                f"`python -m tools.vocabulary --write`.\n"
                f'"""{self.docstring.strip()}\n"""\n')

    # --- naming --------------------------------------------------------------

    def value_name(self, concept, value):
        """The constant a concept's value is bound to.

        Python only: the console binds no per-value constant, because a
        TypeScript consumer reaches a value through the union type and the
        `as const` array rather than through a name per member.
        """
        return _identifier(f"{concept.name}_{value}")

    def _claims(self, concept):
        if not concept.declared_values:
            return []
        claims = [(self.set_name(concept), f"{concept.name}'s value set")]
        claims += [(self.value_name(concept, value), f"{concept.name}.{value}")
                   for value in concept.declared_values]
        return claims

    def handles(self, concept):
        """The set, plus one handle per value — Python binds both."""
        handles = super().handles(concept)
        for value in concept.declared_values:
            handles[self.value_name(concept, value)] = frozenset({value})
        return handles

    # --- rendering -----------------------------------------------------------

    def _body(self, concept):
        if not concept.declared_values:
            return []
        names = [self.value_name(concept, value)
                 for value in concept.declared_values]
        # `repr`, not an f-string into quotes. A concept may override
        # `token_pattern` with any regular expression, so a value carrying a
        # quote or a backslash is a registry the compiler accepts — and
        # interpolating one would emit Python that is broken or, worse, valid
        # and wrong. Single quotes are what `repr` produces, and what the SDK's
        # generated exception hierarchy already uses.
        lines = [f"{name} = {value!r}"
                 for name, value in zip(names, concept.declared_values)]
        lines.append("")
        lines.append(f"{self.set_name(concept)} = frozenset({{")
        lines += [f"    {name}," for name in names]
        lines.append("})")
        return lines


_BACKEND_DOCSTRING = """Canonical vocabulary constants, generated from the registry.

`domain-vocabulary/` at the git root is the checked-in statement of what every
UBB-owned concept is called and what values it may take (ADR-0008 §2). This
module is that registry rendered as Python, so a model or a service holds a
canonical value by REFERENCE and the backend cannot keep a second copy of it
that drifts.

Two names per value set, and the difference between them is load-bearing:

    <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
    <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
                            that is not in it is still legal, so this set never
                            decides a rejection (ADR-0003).

Three things are deliberately absent:

- **Retired terms.** Naming one would plant a forbidden word in a file nobody
  may hand-edit. The forbidden-term sweep reads `retired_aliases` from the
  registry itself, which is the copy that can actually be corrected.
- **Label keys and the English.** Console content: wording changes far more
  often than the token underneath it (ADR-0008 §4).
- **Imports.** Literals only, so this module is safe to import from a
  migration, a management command or a settings-free tool, and can never take
  part in an import cycle."""


_SDK_DOCSTRING = """Canonical vocabulary constants, generated from the registry.

`domain-vocabulary/` in the UBB repository is the checked-in statement of what
every UBB-owned concept is called and what values it may take (ADR-0008 §2).
This module is that registry rendered as Python, so **a value the API can
return is a value this SDK can name**: an integrator branches on a constant
rather than on a string they typed from memory into their own code.

Two names per value set, and the difference between them is load-bearing:

    <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
    <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
                            that is not in it is still legal (ADR-0003), so
                            this set never decides a rejection. An SDK that
                            refused an unrecognised value would break its
                            callers on the day UBB adds one.

Three things are deliberately absent:

- **Retired terms.** Naming one would plant a forbidden word in a file nobody
  may hand-edit. The forbidden-term sweep reads `retired_aliases` from the
  registry itself, which is the copy that can actually be corrected.
- **Label keys and the English.** Console content: wording changes far more
  often than the token underneath it (ADR-0008 §4), and an SDK has no user to
  render one to.
- **Imports, and a re-export.** Literals only, so importing this module can
  neither fail nor join an import cycle. It is deliberately NOT star-exported
  from `ubb/__init__.py`: that would put every concept's constants in the
  package's top-level namespace, and a hand-written re-export list would be the
  second copy of every name this artifact exists to abolish. Reach it by
  module::

      from ubb import vocabulary

      if response.status == vocabulary.TASK_STATUS_COMPLETED:
          ..."""


class BackendConstants(_PythonConstants):
    """The Django platform's generated vocabulary constants."""

    path = "ubb-platform/core/vocabulary.py"
    docstring = _BACKEND_DOCSTRING


class SdkConstants(_PythonConstants):
    """The Python SDK's generated vocabulary constants.

    A separate target rather than a copy of the backend's file, because the SDK
    is a separately installed distribution: it cannot import `core.vocabulary`,
    and vendoring it would be the drifting second copy again. Same renderer,
    two homes, one authored source.
    """

    path = "ubb-sdk/ubb/vocabulary.py"
    docstring = _SDK_DOCSTRING


# ---------------------------------------------------------------------------
# The console's value lists and label keys
# ---------------------------------------------------------------------------

_CONSOLE_DOCSTRING = """Canonical vocabulary values and label keys, generated from the registry.

`domain-vocabulary/` at the git root is the checked-in statement of what every
UBB-owned concept is called and what values it may take (ADR-0008 §2). This
module is that registry rendered as TypeScript, so the console holds a
canonical value by REFERENCE and cannot keep a second copy of it that drifts.

Three names per valued concept:

    <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
    <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
                            that is not in it is still legal, so this array
                            never decides a rejection (ADR-0003) and the
                            concept's type admits any string.
    <CONCEPT>_LABEL_KEYS    the stable key each value's wording is looked up
                            under — keys, never words.

**The English is deliberately absent.** ADR-0008 §4 draws the line at the point
vocabulary becomes copy: wording, capitalisation and translation change far
more often than the token underneath, and a vocabulary file that became the copy
deck would either turn into an i18n database or privilege English inside the
domain model. The catalogue that attaches words to these keys is the console's
own, and it is checked against these keys both ways (#210).

`satisfies Record<..., string>` on each label map is load-bearing rather than
decorative: it is the console's own compiler proving the map covers every value
of its concept, at the moment a value is added to the registry."""


class ConsoleVocabulary(_Target):
    """The React console's generated value lists and label keys.

    Emitted as `as const` arrays with a derived union type rather than as a
    TypeScript `enum`: an enum is a runtime object the console's
    `erasableSyntaxOnly` build refuses outright, and — more to the point — it
    would give every value a second name, which is the drifting copy this
    artifact exists to abolish.
    """

    path = "apps/ui/src/lib/vocabulary.ts"
    marker = "//"

    def _preamble(self):
        docstring = "\n".join(
            f" * {line}".rstrip() for line in _CONSOLE_DOCSTRING.strip().splitlines())
        return (f"{self.marker} @generated from domain-vocabulary/ — do not "
                f"edit by hand.\n"
                f"{self.marker} Regenerate with "
                f"`python -m tools.vocabulary --write`.\n"
                f"\n/**\n{docstring}\n */\n")

    # --- naming --------------------------------------------------------------

    def label_keys_name(self, concept):
        return _identifier(f"{concept.name}_label_keys")

    def type_name(self, concept):
        """The union type over the concept's declared values."""
        return _pascal_case(concept.name)

    def known_type_name(self, concept):
        """The union over an `open` concept's KNOWN values.

        A separate name because the two are genuinely different types: the
        concept's own type admits any string, and this one is the closed set
        UBB recognises today — which is what a label map may be total over.
        """
        return f"{self.type_name(concept)}Known"

    def label_key(self, concept, value):
        """The stable key a value's wording is looked up under.

        `<label_key_prefix>.<value>`, verbatim. A dotted webhook value gives a
        three-segment key, and that is correct rather than tolerated: the
        prefix is fixed per concept, so the key is unambiguous and losslessly
        reversible — which a collapsed spelling would not be.
        """
        return f"{concept.label_key_prefix}.{value}"

    def _claims(self, concept):
        if not concept.declared_values:
            return []
        claims = [
            (self.set_name(concept), f"{concept.name}'s value list"),
            (self.label_keys_name(concept), f"{concept.name}'s label keys"),
            (self.type_name(concept), f"{concept.name}'s type"),
        ]
        if concept.known_values:
            claims.append((self.known_type_name(concept),
                           f"{concept.name}'s known-value type"))
        # Label keys share ONE namespace across concepts — the console's
        # catalogue is a flat map — so two concepts whose prefix and value
        # coincide would put one concept's wording under the other's key. The
        # compiler cannot see this: `label_key_prefix` is free to repeat as far
        # as the registry is concerned, and only this surface flattens them.
        claims += [(self.label_key(concept, value),
                    f"{concept.name}.{value}'s label key")
                   for value in concept.declared_values]
        return claims

    def handles(self, concept):
        """The array, the label-key map, and the type that carries the values.

        No per-value handle: this surface binds no constant per member (see
        :meth:`_PythonConstants.value_name`), so holding is all-or-nothing here.

        AN OPEN CONCEPT'S OWN TYPE IS NOT A HANDLE, and this is the subtle one.
        It renders as ``<Known> | (string & {})`` precisely so a value UBB has
        never seen stays legal (ADR-0003) — which means a consumer typing a
        field with it has enumerated nothing. Only the KNOWN type carries the
        values, which is why it is a separate name at all.
        """
        handles = super().handles(concept)
        if not concept.declared_values:
            return handles
        whole = frozenset(concept.declared_values)
        handles[self.label_keys_name(concept)] = whole
        handles[self.known_type_name(concept) if concept.known_values
                else self.type_name(concept)] = whole
        return handles

    # --- rendering -----------------------------------------------------------

    def _body(self, concept):
        if not concept.declared_values:
            return []
        lines = [f"export const {self.set_name(concept)} = ["]
        lines += [f"  {_ts_string(value)}," for value in concept.declared_values]
        lines.append("] as const;")
        lines.append("")
        lines += self._types(concept)
        lines.append("")
        lines.append(f"export const {self.label_keys_name(concept)} = {{")
        lines += [f"  {_ts_string(value)}: "
                  f"{_ts_string(self.label_key(concept, value))},"
                  for value in concept.declared_values]
        lines.append(f"}} as const satisfies Record<{self._label_domain(concept)}, "
                     f"string>;")
        return lines

    def _types(self, concept):
        """The concept's type — and, for an open one, the honest two of them."""
        derived = f"(typeof {self.set_name(concept)})[number]"
        if not concept.known_values:
            return [f"export type {self.type_name(concept)} = {derived};"]
        lines = [f"export type {self.known_type_name(concept)} = {derived};", ""]
        lines += self._comment([
            (0, "An `open` concept: a value UBB has never seen is legal "
                "(ADR-0003), so the type admits any string. The intersection "
                "is what stops TypeScript collapsing the union to `string` "
                "and losing the known values a reader is offered."),
        ])
        lines.append(f"export type {self.type_name(concept)} = "
                     f"{self.known_type_name(concept)} | (string & {{}});")
        return lines

    def _label_domain(self, concept):
        """What a concept's label map must be total over.

        The KNOWN values for an open concept, not its type: a map keyed by
        `string` would be total over nothing, and the `satisfies` check —
        which is the whole reason the map is written this way — would stop
        proving anything at all.
        """
        return (self.known_type_name(concept) if concept.known_values
                else self.type_name(concept))


BACKEND_CONSTANTS = BackendConstants()
CONSOLE_VOCABULARY = ConsoleVocabulary()
SDK_CONSTANTS = SdkConstants()

#: Every artifact generated from the registry. Adding one here gives it the
#: zero-diff gate, `--write`, and the CLI's report at once — which is the point
#: of the list existing at all.
TARGETS = (BACKEND_CONSTANTS, CONSOLE_VOCABULARY, SDK_CONSTANTS)


# ---------------------------------------------------------------------------
# The decision rule, rendered once for every language
# ---------------------------------------------------------------------------

def _decision_rule_blocks(concept):
    """A concept's `value_semantics` as comment blocks.

    As a COMMENT in every target, not a table: these artifacts are literals,
    and a half-imported rule invites a caller to consult two of its rows and
    infer the third. The registry holds the rule as data — that is where a
    consumer that wants to evaluate it should read it, through the compiler
    that already proved it total.

    One implementation for all three targets, so the rule a reader meets in the
    console is the rule the backend states, down to the indentation.
    """
    semantics = concept.value_semantics
    if semantics is None:
        return []
    blocks = [
        (0, _BREAK),
        (0, "Decision rule, declared as registry data and proved total and "
            "unambiguous by the compiler:"),
        (0, _BREAK),
        (2, semantics.summary.strip()),
    ]
    for case in semantics.cases:
        condition = ", ".join(f"{name}={state}" for name, state in case.when)
        blocks += [
            (0, _BREAK),
            (_RULE_INDENT, condition),
            (_ANSWER_INDENT, f"-> {case.then}"),
            (_REASON_INDENT, case.because.strip()),
        ]
    return blocks


# ---------------------------------------------------------------------------
# Checking and writing
# ---------------------------------------------------------------------------

#: The two ways an artifact fails to be what the registry produces. Module
#: constants for the same reason ``errors.py``'s codes are: a test asserts on
#: the reason, so rewording one never turns a control into a test that passes
#: for the wrong reason.
MISSING = "missing"
DIFFERS = "differs"


@dataclass(frozen=True)
class Stale:
    """One artifact that is not what the registry produces.

    ``reason`` separates :data:`MISSING` from :data:`DIFFERS` because they are
    different faults with different fixes, and "no differences found" must
    never be what a deleted artifact looks like.
    """
    path: str
    reason: str


def _compare(target, registry, repo_root):
    """``(rendered bytes, reason or None)`` for one target.

    The one place a committed artifact is compared to its registry, so the
    check and the rewrite cannot drift apart — and the render happens once,
    rather than twice for the sake of not repeating three lines.

    The comparison is over BYTES, not decoded text. Decoding would fold CRLF
    into LF and call a Windows working copy current, which is exactly the file
    `.gitattributes` pins to LF and CI compares with `git status`: the tool
    would then report "up to date" about a file git reports as modified. Byte
    equality makes the two agree, and makes `--write` repair the anomaly rather
    than skip over it.
    """
    rendered = target.render(registry).encode("utf-8")
    path = Path(repo_root) / target.path
    if not path.is_file():
        return rendered, MISSING
    if path.read_bytes() != rendered:
        return rendered, DIFFERS
    return rendered, None


def stale_targets(registry, repo_root):
    """Every target whose committed bytes are not what ``registry`` renders.

    The single predicate behind both verdicts — the CLI's and CI's — so a
    contributor's local answer cannot differ from the board's.
    """
    return tuple(Stale(target.path, reason) for target in TARGETS
                 if (reason := _compare(target, registry, repo_root)[1]))


def write_targets(registry, repo_root):
    """Regenerate every stale target; return the paths actually rewritten.

    **Every target is rendered before any is written.** A registry can be valid
    and still be unrenderable on one surface — that is what
    :class:`GenerationFailed` exists to say — and with more than one target
    that failure would otherwise arrive halfway through, leaving some artifacts
    rewritten and the rest stale while the command exits non-zero. The CLI
    already refuses to write from an invalid registry for exactly this reason;
    a surface that cannot express a valid one deserves the same treatment,
    because a half-regenerated working tree is worse than an untouched one.

    Written as bytes, so the newlines are the renderer's LF on every platform
    rather than whatever the local text mode would substitute. These artifacts
    are byte-compared: a contributor on Windows regenerating a CRLF file would
    otherwise hand CI a diff nobody could see in a review.
    """
    rendered = [(target, *_compare(target, registry, repo_root))
                for target in TARGETS]

    written = []
    for target, content, reason in rendered:
        if reason is None:
            continue
        path = Path(repo_root) / target.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        written.append(target.path)
    return tuple(written)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _identifier(text):
    """A registry token as a SCREAMING_SNAKE constant name.

    Non-alphanumerics collapse to `_`, so the webhook catalogue's
    `<owner>.<past-tense state entered>` names (ADR-0006 §5) render as
    `TASK_COMPLETED` rather than as `TASK.COMPLETED`, which is not an
    identifier at all. Any collision the collapse creates is caught by
    :meth:`_Target._check_for_collisions`, not left to chance.
    """
    name = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").upper()
    if not name.isidentifier():
        raise GenerationFailed(
            f"{text!r} does not render to a name (got {name!r}) — the "
            f"registry admits it, this surface cannot express it"
        )
    return name


def _pascal_case(text):
    """A registry token as a TypeScript type name.

    Same collapse as :func:`_identifier`, capitalised per run rather than
    upper-cased whole, because a type name is read as words. `task_status`
    becomes `TaskStatus`; any collision it creates is refused rather than
    resolved by whichever concept sorts last.
    """
    name = "".join(part[:1].upper() + part[1:]
                   for part in re.split(r"[^0-9A-Za-z]+", text) if part)
    if not name or not name.isidentifier():
        raise GenerationFailed(
            f"{text!r} does not render to a type name (got {name!r}) — the "
            f"registry admits it, this surface cannot express it"
        )
    return name


def _ts_string(text):
    """A registry token as a TypeScript string literal.

    `json.dumps` rather than an f-string into quotes, for the reason the Python
    targets use `repr`: a concept may override `token_pattern` with any regular
    expression, so a value carrying a quote or a backslash is one the compiler
    accepts, and interpolating it would emit TypeScript that is broken or —
    for the backslash — valid and quietly wrong. JSON string syntax is a subset
    of TypeScript's, and escaping non-ASCII keeps the artifact byte-identical
    whatever a checkout's encoding does.
    """
    return json.dumps(text)
