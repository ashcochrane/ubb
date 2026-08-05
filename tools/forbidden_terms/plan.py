"""The sweep's declared plan: where it looks, and what it deliberately does not.

#154 §14 is the whole reason this module exists. It flags that the forbidden-term
sweep *"will have false positives in vendored code, migration files carrying
historical column names, and the frozen dated documents"*, and then names the
danger in the remedy: **"an over-broad exclusion silently disarms it."**

So the exclusions are not a glob buried in a walker. They are declared data with
three properties the sweep enforces against itself:

1. **Enumerated.** A pattern is an exact tracked path or a `dir/**` prefix, and
   nothing else. There is no wildcard language here on purpose — a matcher with
   surprising corners is itself a way to disarm a gate, and a reviewer must be
   able to read a rule and know what it covers.
2. **Counted.** Each rule declares exactly how many tracked files it removes from
   the sweep. Widening one changes the number, and the number is in the diff.
3. **Totally accounted.** Every tracked file is either swept or matched by
   exactly one rule. There is no third category, which is what makes *narrowing*
   the sweep impossible too: a surface quietly dropped from the walk is a file
   with no rule, and that fails.

The third is the one worth dwelling on. Counting exclusions catches a blind spot
that grows. It does not catch a sweep that stopped reading `ubb-sdk/` — for that
the walk has to start from the whole tree rather than from a list of roots, and
the roots have to be an *output* of the accounting rather than an input to it.
"""

from dataclasses import dataclass

import yaml

from tools.forbidden_terms import errors as codes
from tools.forbidden_terms.errors import SweepError
from tools.vocabulary.loader import DuplicateKey, load_yaml

PLAN_FILE = "forbidden-term-sweep.yaml"
PLAN_PATH = f"gates/{PLAN_FILE}"

#: An exclusion that never ends, and one that ends at the cutover squash. #155
#: §5.4 deletes the whole historical-migration category rather than excusing it,
#: so that rule carries the slice that deletes it and cannot outlive its reason.
PERMANENT = "permanent"
UNTIL_SLICE_8 = "until_slice_8"
PERMANENCES = (PERMANENT, UNTIL_SLICE_8)

#: The slice whose squash deletes the ending category. Named here so the plan
#: cannot claim an end date against a slice that does not exist.
ENDING_SLICE = "slice_8"

PLAN_SECTIONS = ("version", "areas", "fallback_area", "anchors", "exclusions")
REQUIRED_SECTIONS = ("areas", "fallback_area", "anchors", "exclusions")

AREA_FIELDS = ("root", "summary")
RULE_FIELDS = ("id", "paths", "reason", "permanence", "files")

_WILDCARD = set("*?[]")


@dataclass(frozen=True)
class Area:
    """One region of the tree, for reporting and for owning a ledger entry.

    The registry's four surfaces are NOT declared here — they are read from
    `domain-vocabulary/consumers.yaml`, which already states where the backend,
    the console, the SDK and the committed contract live. A second copy of those
    roots is a second thing to keep true.
    """
    name: str
    root: str
    summary: str
    #: Where the area came from — the registry's consumer surfaces, or this plan.
    declared_by: str

    def contains(self, path):
        return bool(self.root) and (path == self.root
                                    or path.startswith(self.root + "/"))


@dataclass(frozen=True)
class ExclusionRule:
    """One declared, counted reason a file is not swept."""
    id: str
    paths: tuple
    reason: str
    permanence: str
    files: int

    def matches(self, path):
        return any(_matches(pattern, path) for pattern in self.paths)

    @property
    def is_permanent(self):
        return self.permanence == PERMANENT


@dataclass(frozen=True)
class Plan:
    areas: tuple
    fallback_area: str
    anchors: tuple
    exclusions: tuple

    def area_of(self, path):
        """The most specific declared area containing ``path``.

        Longest root wins, so `ubb-platform/docs/plans/` resolving to the
        backend rather than to the living docs is a decision the roots make
        rather than one the iteration order makes.
        """
        best = None
        for area in self.areas:
            if area.contains(path) and (best is None
                                        or len(area.root) > len(best.root)):
                best = area
        return best.name if best is not None else self.fallback_area

    @property
    def area_names(self):
        return tuple(sorted({area.name for area in self.areas}
                            | {self.fallback_area}))


def _matches(pattern, path):
    """Exact path, or a `dir/**` prefix. Deliberately the whole language."""
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return path == pattern


def _pattern_fault(pattern, where):
    """Why ``pattern`` may not be used, or None.

    Refusing a pattern is cheaper than auditing what one turned out to mean.
    """
    if not isinstance(pattern, str) or not pattern.strip():
        return f"{pattern!r} is not a path"
    if "\\" in pattern:
        return (f"`{pattern}` uses a backslash. Paths here are POSIX, because "
                f"that is what `git ls-files` reports on every platform.")
    if pattern.startswith("/") or pattern.startswith("./") or ".." in pattern:
        return (f"`{pattern}` is not repository-relative. A pattern is a path "
                f"from the git root, with no leading slash and no `..`.")
    body = pattern[:-3] if pattern.endswith("/**") else pattern
    if _WILDCARD & set(body):
        return (f"`{pattern}` uses a wildcard. An exclusion is an exact tracked "
                f"path or a `dir/**` prefix and nothing else — a matcher with "
                f"corners is itself a way to disarm a gate (#154 §14).")
    if pattern.endswith("/**") and not body:
        return ("`**` excludes the entire repository. There is no reason to "
                "write that which is not the reason this gate exists.")
    return None


def load_plan(repo_root, surfaces, slices, plan_path=None):
    """Read and validate ``gates/forbidden-term-sweep.yaml``.

    ``surfaces`` is the registry's ``consumers.yaml`` surface mapping, so the
    four declared surfaces become areas without being restated. ``slices`` is
    ``slices.yaml``'s, so an exclusion that claims to end at the cutover is
    checked against a slice that exists.

    ``plan_path`` reads the declaration from somewhere else while area roots and
    anchors still resolve against ``repo_root``. That is what the negative
    controls need: a mutated plan against a real tree, without writing to the
    committed file and hoping a `finally` runs.

    Returns ``(plan, faults)``. A caller with faults has no plan: the sweep must
    not run against a declaration it could not read, because "found nothing" and
    "looked nowhere" are the same output.
    """
    path = plan_path if plan_path is not None else repo_root / PLAN_PATH
    if not path.is_file():
        return None, (SweepError(codes.PLAN_MISSING, PLAN_PATH,
                                 "the sweep's declared plan is missing"),)
    try:
        document = load_yaml(path.read_text(encoding="utf-8"))
    except DuplicateKey as duplicate:
        return None, (SweepError(codes.PLAN_INVALID, PLAN_PATH,
                                 str(duplicate)),)
    except (yaml.YAMLError, UnicodeDecodeError) as problem:
        return None, (SweepError(codes.PLAN_INVALID, PLAN_PATH,
                                 str(problem).replace("\n", " ")),)
    if not isinstance(document, dict):
        return None, (SweepError(codes.PLAN_INVALID, PLAN_PATH,
                                 "the plan is not a mapping"),)

    faults = []
    for section in REQUIRED_SECTIONS:
        if section not in document:
            faults.append(SweepError(codes.PLAN_MISSING_FIELD, PLAN_PATH,
                                     f"the plan declares no `{section}`"))
    for section in document:
        if section not in PLAN_SECTIONS:
            faults.append(SweepError(
                codes.PLAN_UNKNOWN_FIELD, PLAN_PATH,
                f"`{section}` is not a section of this plan. It holds exactly "
                f"{', '.join(PLAN_SECTIONS)}."))
    if faults:
        return None, tuple(faults)

    areas, area_faults = _areas(document["areas"], surfaces, repo_root)
    faults.extend(area_faults)

    # The residual: every file no declared root contains. It is NOT itself a
    # rooted area — its whole definition is "the rest" — so it must not reuse a
    # rooted area's name, which would make one name mean two different sets.
    fallback = document["fallback_area"]
    if not isinstance(fallback, str) or not fallback.strip():
        faults.append(SweepError(
            codes.UNKNOWN_FALLBACK_AREA, PLAN_PATH,
            f"the fallback area {fallback!r} is not a name. Every file the "
            f"declared roots do not contain is reported against it, so a "
            f"ledger entry needs it to be something."))
    elif any(area.name == fallback for area in areas):
        faults.append(SweepError(
            codes.UNKNOWN_FALLBACK_AREA, PLAN_PATH,
            f"`{fallback}` is both a rooted area and the residual one. One "
            f"name would then mean two different sets of files."))

    anchors, anchor_faults = _anchors(document["anchors"], repo_root)
    faults.extend(anchor_faults)

    exclusions, rule_faults = _exclusions(document["exclusions"], slices)
    faults.extend(rule_faults)

    if faults:
        return None, tuple(faults)
    return Plan(areas=areas, fallback_area=fallback, anchors=anchors,
                exclusions=exclusions), ()


def _areas(document, surfaces, repo_root):
    """The registry's surfaces, plus the plan's own. Never the same root twice."""
    areas = [Area(name=name, root=surface.root.rstrip("/"),
                  summary=surface.summary, declared_by="consumers.yaml")
             for name, surface in sorted(surfaces.items())]
    declared_roots = {area.root for area in areas}

    faults = []
    if not isinstance(document, dict):
        return tuple(areas), (SweepError(codes.AREA_INVALID, PLAN_PATH,
                                         "`areas` is not a mapping"),)
    for name, body in sorted(document.items()):
        where = f"{PLAN_PATH}: {name}"
        if not isinstance(body, dict):
            faults.append(SweepError(codes.AREA_INVALID, where,
                                     "an area body is not a mapping"))
            continue
        unknown = set(body) - set(AREA_FIELDS)
        missing = set(AREA_FIELDS) - set(body)
        if unknown or missing:
            faults.append(SweepError(
                codes.AREA_INVALID, where,
                f"an area carries exactly {', '.join(AREA_FIELDS)}"
                + (f"; unknown: {', '.join(sorted(unknown))}" if unknown else "")
                + (f"; missing: {', '.join(sorted(missing))}" if missing else "")))
            continue
        root = body["root"]
        if not isinstance(root, str) or not root.strip():
            faults.append(SweepError(codes.AREA_INVALID, where,
                                     "`root` is not a path"))
            continue
        root = root.rstrip("/")
        if any(area.name == name for area in areas):
            faults.append(SweepError(
                codes.AREA_SHADOWS_SURFACE, where,
                f"`{name}` is already a surface the registry declares in "
                f"consumers.yaml. Declaring it again here is a second copy of "
                f"a root that has to stay true."))
            continue
        if root in declared_roots:
            faults.append(SweepError(
                codes.AREA_SHADOWS_SURFACE, where,
                f"`{root}` is already a declared area's root. Two areas over "
                f"one root make `area_of` a question about iteration order."))
            continue
        if not (repo_root / root).is_dir():
            faults.append(SweepError(
                codes.AREA_ROOT_MISSING, where,
                f"`{root}` is not a directory in the repository"))
            continue
        declared_roots.add(root)
        areas.append(Area(name=name, root=root, summary=body["summary"],
                          declared_by=PLAN_FILE))
    return tuple(areas), tuple(faults)


def _anchors(document, repo_root):
    """Files the sweep must be shown to have read. See `sweep.vacuity_faults`."""
    if not isinstance(document, list) or not document:
        return (), (SweepError(codes.ANCHOR_MISSING, PLAN_PATH,
                               "`anchors` is not a non-empty list"),)
    faults = []
    anchors = []
    for entry in document:
        if not isinstance(entry, str) or not entry.strip():
            faults.append(SweepError(codes.ANCHOR_MISSING, PLAN_PATH,
                                     f"{entry!r} is not a path"))
            continue
        if not (repo_root / entry).is_file():
            faults.append(SweepError(
                codes.ANCHOR_MISSING, f"{PLAN_PATH}: {entry}",
                f"`{entry}` is not a file in the repository. An anchor that "
                f"does not exist proves nothing about what was read."))
            continue
        anchors.append(entry)
    return tuple(anchors), tuple(faults)


def _exclusions(document, slices):
    if not isinstance(document, list) or not document:
        return (), (SweepError(codes.RULE_INVALID, PLAN_PATH,
                               "`exclusions` is not a non-empty list"),)
    faults = []
    rules = []
    seen = set()
    for body in document:
        if not isinstance(body, dict):
            faults.append(SweepError(codes.RULE_INVALID, PLAN_PATH,
                                     "an exclusion rule is not a mapping"))
            continue
        rule_id = body.get("id")
        where = f"{PLAN_PATH}: {rule_id}"
        missing = [f for f in RULE_FIELDS if f not in body]
        if missing:
            faults.append(SweepError(
                codes.RULE_MISSING_FIELD, where,
                f"an exclusion rule requires {', '.join(RULE_FIELDS)}; "
                f"missing: {', '.join(missing)}"))
            continue
        unknown = sorted(set(body) - set(RULE_FIELDS))
        if unknown:
            faults.append(SweepError(
                codes.RULE_UNKNOWN_FIELD, where,
                f"unknown field(s): {', '.join(unknown)}"))
            continue
        if not isinstance(rule_id, str) or not rule_id.strip():
            faults.append(SweepError(codes.RULE_INVALID, where,
                                     "`id` is not a name"))
            continue
        if rule_id in seen:
            faults.append(SweepError(codes.DUPLICATE_RULE_ID, where,
                                     f"`{rule_id}` is declared twice"))
            continue
        seen.add(rule_id)

        reason, permanence, count = (body["reason"], body["permanence"],
                                     body["files"])
        if not isinstance(reason, str) or not reason.strip():
            faults.append(SweepError(codes.RULE_INVALID, where,
                                     "`reason` is not stated"))
            continue
        # `bool` is an `int` in Python, and `files: true` is not a count.
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            faults.append(SweepError(
                codes.RULE_INVALID, where,
                f"`files` is {count!r}, not a count of the tracked files this "
                f"rule removes from the sweep"))
            continue
        if permanence not in PERMANENCES:
            faults.append(SweepError(
                codes.UNKNOWN_PERMANENCE, where,
                f"`{permanence}` is not a permanence. A rule is `{PERMANENT}` "
                f"or `{UNTIL_SLICE_8}`, and nothing else — an exclusion with no "
                f"stated end is how one outlives its reason."))
            continue
        if permanence == UNTIL_SLICE_8:
            if ENDING_SLICE not in slices:
                faults.append(SweepError(
                    codes.UNKNOWN_PERMANENCE, where,
                    f"`{UNTIL_SLICE_8}` names a slice slices.yaml does not "
                    f"declare"))
                continue
            if ENDING_SLICE not in reason:
                faults.append(SweepError(
                    codes.PERMANENCE_UNSTATED, where,
                    f"the reason must name `{ENDING_SLICE}` as the point this "
                    f"exclusion is deleted rather than renewed (#155 §5.4). A "
                    f"reader of the reason has to see the end date too."))
                continue

        patterns = body["paths"]
        if not isinstance(patterns, list) or not patterns:
            faults.append(SweepError(codes.RULE_INVALID, where,
                                     "`paths` is not a non-empty list"))
            continue
        bad = [_pattern_fault(p, where) for p in patterns]
        if any(bad):
            for problem in bad:
                if problem:
                    faults.append(SweepError(codes.BAD_PATTERN, where, problem))
            continue
        rules.append(ExclusionRule(id=rule_id, paths=tuple(patterns),
                                   reason=reason, permanence=permanence,
                                   files=count))
    return tuple(rules), tuple(faults)
