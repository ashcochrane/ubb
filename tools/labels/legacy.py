"""What still manufactures English out of a token, and where it is reachable from.

ADR-0008 §4.3 reverses #154 §9.1: **silent humanisation of a canonical concept
is a defect**, not a soft landing. Title-casing a retired token invents a name
nobody chose, which is the authority ADR-0006 spent thirteen documents
establishing. (ADR-0008 §4.3 names the billing-mode example; this module does
not repeat the retired word, because #206's sweep is right that a debt is not a
licence for it to reach further.)

The old behaviour cannot simply be deleted — `apps/ui/src/lib/labels.ts` is
imported by forty-seven files, and #210 is explicit that slice 0 ends when the
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

## Four stated limits, recorded rather than left to be discovered

1. **Reach is measured one hop.** A file importing `humanize` is a site; a file
   importing something that *itself* humanises is not. `settings.ts` is the
   live case — it re-exports `auditActionLabel`, which falls back to `humanize`
   — so its ledger entry says so. Following the graph would mean resolving
   TypeScript imports from Python, and the honest cheap answer is to name the
   hop and record where it leaks. What closes the gap the hop leaves open is
   :attr:`Legacy.importers`: every file importing the adapter AT ALL is pinned,
   so the second hop cannot GROW even where this module cannot follow it.
2. **The adapter's exports are classified by name, not by parsing TypeScript.**
   Every one is either a ledgered debt or a pinned entry in
   :data:`DECLARED_NON_LABEL_EXPORTS` with the reason it carries no wording.
   There is deliberately no rule-based "and anything shaped like a value list
   is fine" escape: a category defined by what is left over grows in silence,
   which is the thing the pinning exists to prevent. An export this module
   cannot classify is a fault, never a pass.
3. **Only the console is swept.** The SDK and the backend hold no wording at
   all, which is G2's and G3's subject rather than this gate's, and neither
   ships a humaniser — asserted rather than assumed.
4. **Only the ADAPTER's maps are enumerated, not every map in the console.**
   `AUDIT_NOUN_LABELS` in `features/settings/lib/settings.ts` is a hand-written
   value map living outside this file, and a new one like it would be invisible
   here. That is #227's ruling applied rather than an oversight: a TypeScript
   `as const` object is as often a query key or a hint as it is vocabulary, and
   a pinned count over all of them would pin noise and be raised until it
   stopped failing. The three live cases are recorded instead —
   `AUDIT_NOUN_LABELS` in that file's own ledger entry; `REWARD_TYPE_HINTS` in
   `features/referrals/components/program-form.tsx`; and `PRODUCT_DESCRIPTIONS`
   in `lib/products.ts` (#241). The last two are explanatory copy rather than
   the name of a value, and therefore permanently out of scope under ADR-0008
   §4.5 — which is also why neither is a debt this gate could ever clear.
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
#:
#: The six value lists and three types are pinned BY NAME rather than matched by
#: shape. A rule saying "an `as const` array is a value list, and a value list
#: is G2's subject" would be true of these nine and false of the tenth somebody
#: adds, and nothing would say so.
_VALUE_SET = ("a canonical value set the console still restates. Not this "
              "gate's subject: G2 and G3 ask whether a consumer holds a value "
              "BY REFERENCE, and this file already has their ledger entries")
_BY_REFERENCE = ("a canonical value set this file now holds BY REFERENCE, "
                 "aliasing the generated `@/lib/vocabulary` (#241). It stays "
                 "here because the registry names this file as the console's "
                 "consumer of the concept; it carries no words either way")
_DERIVED_TYPE = ("a type derived from the value list beside it. A type carries "
                 "no words, so there is nothing for a catalogue to own")
DECLARED_NON_LABEL_EXPORTS = {
    HUMANISER: (
        "the adapter's mechanism, not a use of it. Deleting it is the whole "
        "point of the ledger below reaching zero"),
    "roleRank": (
        "ranks a role for a floor comparison and returns a number. It carries "
        "no words, so there is nothing for a catalogue to own"),
    "BILLING_MODES": _VALUE_SET,
    "COSTING_METHODS": _BY_REFERENCE,
    "COSTING_STATUSES": _BY_REFERENCE,
    "PRODUCTS": _BY_REFERENCE,
    "ROLES": _VALUE_SET,
    "ANALYTICS_DIMENSIONS": _VALUE_SET,
    "TIMESERIES_GROUP_BY": _VALUE_SET,
    "WEBHOOK_EVENT_TYPES": _VALUE_SET,
    "BillingMode": _DERIVED_TYPE,
    "Product": _BY_REFERENCE,
    "Role": _DERIVED_TYPE,
}

_EXPORT = re.compile(
    r"^export\s+(?:const|function|type|interface|class)\s+(\w+)", re.MULTILINE)
_MAP = re.compile(
    r"^export\s+const\s+(\w+)\s*=\s*" + MAP_CONSTRUCTOR + r"\(", re.MULTILINE)
#: Every construction of a map, exported or not. Compared against `_MAP`'s
#: count: a map declared privately and exported through an `export { … }` clause
#: would otherwise be a map the ledger never hears about.
_ANY_MAP = re.compile(r"=\s*" + MAP_CONSTRUCTOR + r"\(")
#: An `export { … }` clause. The classification above is anchored on
#: declarations, so a clause could export a name it never sees. There are none
#: today and one would be a fault rather than a silent gap.
_EXPORT_CLAUSE = re.compile(r"^export\s*\{", re.MULTILINE)

#: An import OR re-export of the adapter, in either quote style, named or
#: namespace. Quote style matters: the console's eslint configuration declares
#: no `quotes` rule, so a single-quoted specifier is lint-clean and would have
#: been invisible to a `"`-only pattern. A namespace import reaches EVERY export
#: including the humaniser, so it counts as reaching it.
_ADAPTER_IMPORT = re.compile(
    r"(?:import|export)\s+(?:type\s+)?"
    r"(?:\{(?P<named>[^}]*)\}|\*\s+as\s+(?P<namespace>\w+))\s*"
    r"from\s*(?P<quote>[\"'])" + re.escape(ADAPTER_SPECIFIER) + r"(?P=quote)")

#: A declaration of the humaniser, as opposed to a use of it. A second one
#: anywhere in the tree would make the allowlist meaningless, because a caller
#: could reach humanisation without importing the adapter at all.
_HUMANISER_DECLARATION = re.compile(
    r"^\s*(?:export\s+)?(?:function\s+" + HUMANISER + r"\b"
    r"|(?:const|let|var)\s+" + HUMANISER + r"\s*=)", re.MULTILINE)


@dataclass(frozen=True)
class Legacy:
    """Everything the legacy adapter still owes, and everyone who can reach it.

    ``maps`` and ``renderers`` live in the adapter; ``humanisers`` are the files
    that reach the humaniser directly. Those three are the DEBTS, and
    :attr:`sites` is the form a ledger entry records.

    ``importers`` is a different question with a different answer: every console
    file that imports the adapter at all. None of them is a separate debt — each
    imports a map the ledger already owes — but the set must not GROW, because
    every one of those maps still falls back to the humaniser for a value it
    does not recognise. That is #210's *"new or modified code … may not reach
    the adapter"*, and it is the half a ledger of maps cannot express.
    """
    maps: tuple = ()
    renderers: tuple = ()
    humanisers: tuple = ()
    importers: tuple = ()
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
    unclassified = sorted(set(_EXPORT.findall(source))
                          - maps - renderers - set(DECLARED_NON_LABEL_EXPORTS))

    faults = [LabelError(
        codes.ADAPTER_ESCAPED, f"{ADAPTER}::{name}",
        f"`{name}` is exported by the legacy adapter and this gate cannot say "
        f"what it is. Add it to DECLARED_NON_LABEL_EXPORTS with the reason it "
        f"carries no wording, or make it a ledgered debt — an export nobody "
        f"classified is one nobody is watching") for name in unclassified]
    faults += _adapter_shape_faults(source, maps)

    humanisers, importers, escaped = _reach(root, adapter)
    faults += escaped

    return Legacy(
        maps=tuple(sorted(f"{ADAPTER}::{name}" for name in maps)),
        renderers=tuple(sorted(f"{ADAPTER}::{name}" for name in renderers)),
        humanisers=tuple(sorted(humanisers)),
        importers=tuple(sorted(importers)),
        unclassified=tuple(unclassified),
    ), faults


def _adapter_shape_faults(source, maps):
    """The two shapes that would hide a map from the classification above.

    Both are absent today, and both would be silent rather than wrong: a map
    built privately and exported through a clause is a hand-written value map
    the ledger never hears about, which is precisely the debt with no owner
    this gate exists to refuse.
    """
    faults = []
    declared = len(_ANY_MAP.findall(source))
    if declared != len(maps):
        faults.append(LabelError(
            codes.ADAPTER_ESCAPED, ADAPTER,
            f"{declared} value map(s) are built here and {len(maps)} are "
            f"declared as `export const … = {MAP_CONSTRUCTOR}(`. A map exported "
            f"any other way is one the ledger never hears about"))
    if _EXPORT_CLAUSE.search(source):
        faults.append(LabelError(
            codes.ADAPTER_ESCAPED, ADAPTER,
            "this module uses an `export { … }` clause. Every classification "
            "here is anchored on the declaration, so a clause can export a name "
            "the gate never sees — keep exports on the declarations"))
    return faults


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
    """``(humanising sites, importing files, faults)`` for the console.

    A file is a humanising SITE if it names the humaniser in an import or
    re-export of the adapter — or takes a namespace import, which reaches every
    export including the humaniser and is therefore counted as reaching it.
    Importing it and not calling it is still reaching it: the ledger records
    what a slice must come back to, and an unused import is one line of the
    same debt.

    A file is an IMPORTER if it imports the adapter at all. Every export it can
    reach falls back to the humaniser, so the set is what #210's *"may not reach
    the adapter"* is stated over.
    """
    sites, importers, faults = [], [], []
    for path in sorted((root / CONSOLE_ROOT).rglob("*.ts*")):
        if not path.is_file() or path == adapter:
            continue
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        if _HUMANISER_DECLARATION.search(source):
            faults.append(LabelError(
                codes.ADAPTER_ESCAPED, relative,
                f"a second `{HUMANISER}` is declared here. The allowlist is "
                f"over the ONE adapter; a second one means a caller can "
                f"humanise without importing it, and nothing would notice"))
        imports = list(_ADAPTER_IMPORT.finditer(source))
        if not imports:
            continue
        importers.append(relative)
        if any(match.group("namespace")
               or HUMANISER in _specifiers(match.group("named") or "")
               for match in imports):
            sites.append(f"{relative}::{HUMANISER}")
    return sites, importers, faults


def _specifiers(clause):
    """The names in an import's `{ ... }`, aliases resolved to what is imported."""
    return {part.strip().split(" as ")[0].strip()
            for part in clause.split(",") if part.strip()}
