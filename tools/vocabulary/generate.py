"""Render the registry into the artifacts its consumers import.

ADR-0008 §3: **a canonical token is authored once; every other appearance is
generated or verified.** This module is the "generated" half. It turns a
compiled :class:`~tools.vocabulary.compiler.Registry` into source files that
consumers *import*, so a backend model, a console module or an SDK client holds
a canonical value by reference rather than restating the string.

That is what makes the check unfoolable. Scanning backend source for matching
string literals would pass whenever two unrelated places happened to spell the
same word; importing means the two cannot disagree at all, because there is
only one of them.

A target is anything carrying ``path`` and ``render(registry)``. Issue #200
ships one — the backend constants; the console and SDK artifacts (#207, #208)
are new entries in :data:`TARGETS` and inherit the zero-diff gate, the
``--write`` command and the CLI's report without touching this contract.

Two rules hold for every target, and both are tested:

- **Deterministic.** Same registry, same bytes, on any machine and in any
  order. A zero-diff gate over an unstable renderer fails at random, and a gate
  that cries wolf gets disabled rather than obeyed.
- **Refusal over a plausible-looking lie.** Where the registry is valid but
  cannot be rendered honestly — two concepts whose constants would collide on
  one name — generation raises :class:`GenerationFailed`. Silently emitting the
  name once, or twice with the second winning, is not a diff anybody notices.
"""

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

#: Comment and code lines wrap here. Two columns of `# ` prefix land the widest
#: comment line on 79, which is where the rest of the repository sits.
_TEXT_WIDTH = 77
_RULE_WIDTH = 79

#: A decision rule renders as three nested levels — the input assignment, the
#: value it answers, and why. Each sits one step in from the last, so a reader
#: scanning for "what happens when X" can stop at the middle one.
_RULE_INDENT = 2
_ANSWER_INDENT = 4
_REASON_INDENT = 7


class GenerationFailed(Exception):
    """The registry is valid, but an artifact cannot be rendered honestly.

    Distinct from
    :class:`~tools.vocabulary.errors.RegistryInvalid` on purpose: the registry
    passed every rule it declares, and the fault is in what one particular
    surface can faithfully express. A Python constants module cannot give two
    concepts one name; a different surface with different naming rules might
    have no such problem, and should not be told the registry is broken.
    """


# ---------------------------------------------------------------------------
# The backend constants module
# ---------------------------------------------------------------------------

_BANNER = (
    "# @generated from domain-vocabulary/ — do not edit by hand.\n"
    "# Regenerate with `python -m tools.vocabulary --write`.\n"
)

_DOCSTRING = '''"""Canonical vocabulary constants, generated from the registry.

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
  part in an import cycle.
"""
'''

_NO_CONSTANTS_NOTE = (
    "No constants: this kind declares no values by construction. The section "
    "is here so that fact is visible, rather than looking like a concept the "
    "generator lost."
)


class BackendConstants:
    """The Django platform's generated vocabulary constants.

    One flat module of literals rather than a package with a hand-written
    ``__init__`` re-exporting a private ``_generated``: the re-export layer
    would be a second, hand-maintained copy of every name — precisely the thing
    this artifact exists to abolish. What keeps a hand edit out is the banner,
    the LF pin in ``.gitattributes`` and the zero-diff gate, which is the same
    arrangement the SDK's generated exception hierarchy already lives under.
    """

    path = "ubb-platform/core/vocabulary.py"

    def render(self, registry):
        """The module's full source text, for this registry."""
        self._check_for_collisions(registry)
        sections = [self._section(concept, registry)
                    for _, concept in sorted(registry.concepts.items())]
        return _BANNER + _DOCSTRING + "\n" + "\n\n".join(sections)

    # --- naming ------------------------------------------------------------

    def value_name(self, concept, value):
        """The constant a concept's value is bound to."""
        return _identifier(f"{concept.name}_{value}")

    def set_name(self, concept):
        """The constant the concept's whole declared set is bound to.

        The suffix follows the field the registry populated, which IS the kind
        distinction expressed as data: `closed` requires `values`, `open`
        requires `known_values`.
        """
        suffix = "known_values" if concept.known_values else "values"
        return _identifier(f"{concept.name}_{suffix}")

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
            if not concept.declared_values:
                continue
            declared = [(self.set_name(concept), f"{concept.name}'s value set")]
            declared += [(self.value_name(concept, value),
                          f"{concept.name}.{value}")
                         for value in concept.declared_values]
            for name, described in declared:
                if name in claimed:
                    collisions.append(f"{name} is the constant for both "
                                      f"{claimed[name]} and {described}")
                else:
                    claimed[name] = described
        if collisions:
            raise GenerationFailed(
                f"{self.path} cannot be rendered — one name cannot carry two "
                f"values:\n" + "\n".join(f"  {line}" for line in collisions)
            )

    # --- rendering ---------------------------------------------------------

    def _section(self, concept, registry):
        rule = registry.schema.kinds[concept.kind]
        lines = [_rule_comment(concept.name), "#"]
        lines += _comment(f"{concept.kind} — {rule.summary.strip()}")
        lines += ["#"] + _comment(concept.summary.strip())
        lines += ["#"] + _comment(f"Declared in {concept.source}.")
        lines += self._decision_rule(concept)

        if not concept.declared_values:
            return "\n".join(lines + ["#"] + _comment(_NO_CONSTANTS_NOTE)) + "\n"

        names = [self.value_name(concept, value)
                 for value in concept.declared_values]
        lines.append("")
        # `repr`, not an f-string into quotes. A concept may override
        # `token_pattern` with any regular expression, so a value carrying a
        # quote or a backslash is a registry the compiler accepts — and
        # interpolating one would emit Python that is broken or, worse, valid
        # and wrong. Single quotes are what `repr` produces, and what the SDK's
        # generated exception hierarchy already uses.
        lines += [f"{name} = {value!r}"
                  for name, value in zip(names, concept.declared_values)]
        lines.append("")
        lines.append(f"{self.set_name(concept)} = frozenset({{")
        lines += [f"    {name}," for name in names]
        lines.append("})")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _decision_rule(concept):
        """The concept's `value_semantics`, rendered for a reader.

        As a COMMENT, not a table: the module is literals, and a half-imported
        rule invites a caller to consult two of its rows and infer the third.
        The registry holds the rule as data — that is where a consumer that
        wants to evaluate it should read it, through the compiler that already
        proved it total.
        """
        semantics = concept.value_semantics
        if semantics is None:
            return []
        lines = ["#"] + _comment(
            "Decision rule, declared as registry data and proved total and "
            "unambiguous by the compiler:")
        lines += ["#"] + _comment(semantics.summary.strip(), indent=2)
        for case in semantics.cases:
            condition = ", ".join(f"{name}={state}" for name, state in case.when)
            lines += ["#"] + _comment(condition, indent=_RULE_INDENT)
            lines += _comment(f"-> {case.then}", indent=_ANSWER_INDENT)
            lines += _comment(case.because.strip(), indent=_REASON_INDENT)
        return lines


BACKEND_CONSTANTS = BackendConstants()

#: Every artifact generated from the registry. Adding one here gives it the
#: zero-diff gate, `--write`, and the CLI's report at once — which is the point
#: of the list existing at all.
TARGETS = (BACKEND_CONSTANTS,)


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

    Written as bytes, so the newlines are the renderer's LF on every platform
    rather than whatever the local text mode would substitute. These artifacts
    are byte-compared: a contributor on Windows regenerating a CRLF file would
    otherwise hand CI a diff nobody could see in a review.
    """
    written = []
    for target in TARGETS:
        rendered, reason = _compare(target, registry, repo_root)
        if reason is None:
            continue
        path = Path(repo_root) / target.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rendered)
        written.append(target.path)
    return tuple(written)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _identifier(text):
    """A registry token as a Python constant name.

    Non-alphanumerics collapse to `_`, so the webhook catalogue's
    `<owner>.<past-tense>` names (ADR-0006 §5, arriving with #202) render as
    `TASK_COMPLETED` rather than as `TASK.COMPLETED`, which is not an
    identifier at all. Any collision the collapse creates is caught by
    :meth:`BackendConstants._check_for_collisions`, not left to chance.
    """
    name = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").upper()
    if not name.isidentifier():
        raise GenerationFailed(
            f"{text!r} does not render to a Python name (got {name!r}) — the "
            f"registry admits it, this surface cannot express it"
        )
    return name


def _comment(text, indent=0):
    """``text`` wrapped as `# ` comment lines at the repository's width.

    ``indent`` shifts the wrapped block right, which is what lets a decision
    rule's rows sit under their heading — the whitespace has to be applied here
    because the wrap collapses everything the caller could have written.
    """
    pad = " " * indent
    wrapped = textwrap.wrap(" ".join(text.split()), width=_TEXT_WIDTH - indent,
                            break_long_words=False, break_on_hyphens=False)
    return [f"# {pad}{line}" for line in wrapped] or ["#"]


def _rule_comment(name):
    """`# --- name -----...` padded to the repository's line width."""
    prefix = f"# --- {name} "
    return prefix + "-" * max(3, _RULE_WIDTH - len(prefix))
