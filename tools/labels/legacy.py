"""What still manufactures English out of a token, and where it is reachable from.

ADR-0008 §4.3 reverses #154 §9.1: **silent humanisation of a canonical concept
is a defect**, not a soft landing. Title-casing a retired token invents a name
nobody chose, which is the authority ADR-0006 spent thirteen documents
establishing. (ADR-0008 §4.3 names the billing-mode example; this module does
not repeat the retired word, because #206's sweep is right that a debt is not a
licence for it to reach further.)

The old behaviour cannot simply be deleted — `apps/ui/src/lib/labels.ts` is
imported by fifty-one files, and #210 is explicit that slice 0 ends when the
mechanism is active and regressions are impossible, **not** when all of them
have been rewritten. So it survives as an **explicit legacy adapter**, and this
module is what makes "reachable from allowlisted sites and nowhere else" a fact
rather than an intention:

    from tools.labels import scan_legacy
    legacy, faults = scan_legacy(repo_root)
    legacy.sites          # every debt, as a ledger site string
    legacy.unclassified   # anything the adapter exports that is neither

The allowlist **is the migration ledger**. Nothing is listed twice: a new map
or a new humanising import is a ledger addition, and the ratchet already refuses
one without a reviewed seeding authorisation. That is why this module reports
sites rather than holding a list of its own — a second allowlist beside the
ledger is the drifting copy ADR-0006 §4 warns about, and #203's agreement test
exists because that copy was made once already.

## Three stated limits, recorded rather than left to be discovered

1. **Reach is measured one hop.** A file importing `humanize` is a site; a file
   importing something that *itself* humanises is not. `settings.ts` is the
   live case — it re-exports `auditActionLabel`, which falls back to `humanize`
   — so its ledger entry says so. Following the graph would mean resolving
   TypeScript imports from Python, and the honest cheap answer is to name the
   hop and record where it leaks.
2. **The adapter's exports are classified by shape, not by parsing TypeScript.**
   The file is flat — one `export` per top-level declaration — and the totality
   check below is what stops an unclassified export slipping through as a
   "helper". An export this module cannot classify is a fault, never a pass.
3. **Only the console is swept.** The SDK and the backend hold no wording at
   all, which is G2's and G3's subject rather than this gate's, and neither
   ships a humaniser — asserted below rather than assumed.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from tools.labels import errors as codes
from tools.labels.errors import LabelError

#: The legacy adapter, and the tree that may reach it.
ADAPTER = "apps/ui/src/lib/labels.ts"
CONSOLE_ROOT = "apps/ui/src"

#: The module specifier a console file imports the adapter by. The console has
#: exactly one style — verified by `test_the_adapter_is_imported_one_way`, so a
#: relative import that this pattern would miss fails rather than hides.
ADAPTER_SPECIFIER = "@/lib/labels"

#: The humanising function itself. Exported, because the sites the ledger
#: allowlists call it directly.
HUMANISER = "humanize"

#: The adapter's private map constructor. Renamed from the bare `label` by
#: #210 for one reason: `label` appears in this console as a prop, a variable
#: and a string hundreds of times, so a gate keyed on it would be a gate keyed
#: on a coincidence. This name appears nowhere else in the tree, which makes
#: "every hand-written value map" a set the machine can take rather than one a
#: reviewer has to recognise.
MAP_CONSTRUCTOR = "legacyLabelMap"

#: Exports of the adapter that carry no user-facing wording, each with the
#: reason it is not this gate's subject. A pinned literal rather than a rule,
#: for the reason #206's exclusion set is pinned: a category defined by "what
#: is left over" grows silently, and the growth is exactly what a reader would
#: never notice. An export that is not here and is not a map or a humanising
#: renderer is a FAULT — the gate refuses to guess.
DECLARED_NON_LABEL_EXPORTS = {
    HUMANISER: (
        "the adapter's mechanism, not a use of it. Deleting it is the whole "
        "point of the ledger below reaching zero"),
    "roleRank": (
        "ranks a role for a floor comparison and returns a number. It carries "
        "no words, so there is nothing for a catalogue to own"),
}

_EXPORT = re.compile(
    r"^export\s+(?:const|function|type|interface|class)\s+(\w+)", re.MULTILINE)
_MAP = re.compile(
    r"^export\s+const\s+(\w+)\s*=\s*" + MAP_CONSTRUCTOR + r"\(", re.MULTILINE)
_VALUE_LIST = re.compile(
    r"^export\s+const\s+(\w+)\s*=\s*\[.*?\]\s*as\s+const;", re.MULTILINE | re.DOTALL)
_TYPE = re.compile(r"^export\s+type\s+(\w+)", re.MULTILINE)
_ADAPTER_IMPORT = re.compile(
    r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*\"" + re.escape(ADAPTER_SPECIFIER)
    + r"\"")
#: A declaration of the humaniser, as opposed to a use of it. A second one
#: anywhere in the tree would make the allowlist meaningless, because a caller
#: could reach humanisation without importing the adapter at all.
_HUMANISER_DECLARATION = re.compile(
    r"^\s*(?:export\s+)?(?:function\s+" + HUMANISER + r"\b"
    r"|(?:const|let|var)\s+" + HUMANISER + r"\s*=)", re.MULTILINE)


@dataclass(frozen=True)
class Legacy:
    """Everything the legacy adapter still owes, as ledger sites.

    ``maps`` and ``renderers`` live in the adapter; ``humanisers`` are the
    files that reach it. They are one set for the ledger's purposes and three
    for a reader's, which is why both forms are carried.
    """
    maps: tuple = ()
    renderers: tuple = ()
    humanisers: tuple = ()
    unclassified: tuple = ()

    @property
    def sites(self):
        """Every debt, as the exact string a ledger entry records."""
        return tuple(sorted(self.maps + self.renderers + self.humanisers))


def scan_legacy(repo_root):
    """``(Legacy, faults)`` — the adapter's debts, or why they cannot be counted."""
    root = Path(repo_root)
    adapter = root / ADAPTER
    if not adapter.is_file():
        return Legacy(), [LabelError(
            codes.ADAPTER_MISSING, ADAPTER,
            "the legacy adapter is not where the gate expects it. Moving it is "
            "fine; moving it without telling this gate turns every allowlist "
            "comparison below into a comparison of two empty sets")]

    source = adapter.read_text(encoding="utf-8")
    maps = set(_MAP.findall(source))
    renderers = {name for name in _EXPORT.findall(source)
                 if name not in maps and _humanises(source, name)}
    classified = (maps | renderers | set(_VALUE_LIST.findall(source))
                  | set(_TYPE.findall(source)) | set(DECLARED_NON_LABEL_EXPORTS))
    unclassified = sorted(set(_EXPORT.findall(source)) - classified)

    faults = [LabelError(
        codes.ADAPTER_ESCAPED, f"{ADAPTER}::{name}",
        f"`{name}` is exported by the legacy adapter and this gate cannot say "
        f"what it is. Add it to DECLARED_NON_LABEL_EXPORTS with the reason it "
        f"carries no wording, or make it a ledgered debt — an export nobody "
        f"classified is one nobody is watching") for name in unclassified]

    humanisers, escaped = _reach(root, adapter)
    faults += escaped

    return Legacy(
        maps=tuple(sorted(f"{ADAPTER}::{name}" for name in maps)),
        renderers=tuple(sorted(f"{ADAPTER}::{name}" for name in renderers)),
        humanisers=tuple(sorted(humanisers)),
        unclassified=tuple(unclassified),
    ), faults


def _humanises(source, name):
    """Does the adapter's export ``name`` call the humaniser in its own body?

    The body is taken as the text from this export's declaration to the next
    top-level `export`, which is exact for a flat module and is the second
    limit this module's docstring records. The alternative is a TypeScript
    parser in a suite that deliberately has no Node in it.
    """
    if name == HUMANISER:
        return False
    starts = [match.start() for match in _EXPORT.finditer(source)
              if match.group(1) == name]
    if not starts:
        return False
    start = starts[0]
    following = [match.start() for match in _EXPORT.finditer(source)
                 if match.start() > start]
    body = source[start:following[0] if following else len(source)]
    return re.search(r"\b" + HUMANISER + r"\s*\(", body) is not None


def _reach(root, adapter):
    """``(sites, faults)`` — the console files that import the humaniser.

    A file is a site if it names the humaniser in an import from the adapter.
    Importing it and not calling it is still reaching it: the ledger records
    what a slice must come back to, and an unused import is one line of the
    same debt.
    """
    sites, faults = [], []
    for path in sorted((root / CONSOLE_ROOT).rglob("*.ts*")):
        if not path.is_file() or path == adapter:
            continue
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        if _HUMANISER_DECLARATION.search(source):
            faults.append(LabelError(
                codes.ADAPTER_ESCAPED, relative,
                f"a second `{HUMANISER}` is declared here. The allowlist below "
                f"is over the ONE adapter; a second one means a caller can "
                f"humanise without importing it, and nothing would notice"))
        if any(HUMANISER in _specifiers(clause)
               for clause in _ADAPTER_IMPORT.findall(source)):
            sites.append(f"{relative}::{HUMANISER}")
    return sites, faults


def _specifiers(clause):
    """The names in an import's `{ ... }`, aliases resolved to what is imported."""
    return {part.strip().split(" as ")[0].strip()
            for part in clause.split(",") if part.strip()}
