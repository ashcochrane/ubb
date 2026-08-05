"""The named reasons the forbidden-term sweep can be invalid or fail.

Module constants rather than inline strings, for the reason the rest of the
gate tooling gives: a test asserts on the code, so a reworded message never
silently turns a negative control into a test that passes for the wrong reason.
Same shape as ``tools/gates/errors.py`` and ``tools/vocabulary/errors.py``.

Two families, and the split matters. A ``SWEEP_*`` code says the sweep could not
be trusted to have run — the declared plan is malformed, a file would not decode,
a surface went unread. A ``TERM_*`` code says it ran and found something. A gate
that cannot tell those apart is one bad path away from reporting "no violations"
because it read nothing, which is the failure the vacuity guard exists to refuse.
"""

from dataclasses import dataclass

# --- The declared plan: areas, exclusions, anchors ---------------------------
PLAN_MISSING = "plan_missing"                  # the declaration file is absent
PLAN_INVALID = "plan_invalid"                  # ... or does not parse, or is not a mapping
PLAN_MISSING_FIELD = "plan_missing_field"      # a section the plan must carry
PLAN_UNKNOWN_FIELD = "plan_unknown_field"      # a section declared nowhere

AREA_INVALID = "area_invalid"                  # an area body that is not usable
AREA_ROOT_MISSING = "area_root_missing"        # an area rooted at a path not in the repository
AREA_SHADOWS_SURFACE = "area_shadows_surface"  # ... or at one the registry already declares
UNKNOWN_FALLBACK_AREA = "unknown_fallback_area"  # the fallback names no declared area

RULE_INVALID = "rule_invalid"                  # an exclusion rule body that is not usable
RULE_MISSING_FIELD = "rule_missing_field"
RULE_UNKNOWN_FIELD = "rule_unknown_field"
DUPLICATE_RULE_ID = "duplicate_rule_id"
BAD_PATTERN = "bad_pattern"                    # not an exact path or a `dir/**` prefix
UNKNOWN_PERMANENCE = "unknown_permanence"      # neither permanent nor until_slice_8
PERMANENCE_UNSTATED = "permanence_unstated"    # an ending exclusion whose reason names no end

# --- The accounting, which is the whole point of the exclusion list ----------
UNACCOUNTED_FILE = "unaccounted_file"          # tracked, not swept, matched by no rule
RULE_OVERLAP = "rule_overlap"                  # one file excused twice: the count is then a guess
RULE_COUNT_WRONG = "rule_count_wrong"          # a rule excludes more or fewer files than declared
RULE_INERT = "rule_inert"                      # ... or none at all
RULE_HIDES_ANCHOR = "rule_hides_anchor"        # an exclusion covering a file the sweep must read
ANCHOR_MISSING = "anchor_missing"              # a declared anchor is not in the repository
AREA_UNANCHORED = "area_unanchored"            # an area no anchor proves was read

# --- Reading the tree -------------------------------------------------------
TREE_UNREADABLE = "tree_unreadable"            # `git ls-files` did not answer
FILE_UNDECODABLE = "file_undecodable"          # a swept file is not UTF-8

# --- What the sweep found ---------------------------------------------------
TERM_ON_LIVING_SURFACE = "term_on_living_surface"    # a retired word, with no ledger entry
TERM_SPREAD = "term_spread"                    # ... one that has, but in more files than recorded
LEDGER_EXTENT_OVERSTATED = "ledger_extent_overstated"  # ... or in fewer: part of the debt is paid
LEDGER_ENTRY_STALE = "ledger_entry_stale"      # an entry whose term has left that area entirely
LEDGER_EXTENT_UNPARSED = "ledger_extent_unparsed"   # a G7 entry whose `found` is not `N files`


@dataclass(frozen=True, order=True)
class SweepError:
    """One reason the sweep is invalid, or one thing it found.

    ``location`` names the file and, where there is one, the rule or the term —
    enough for a reader to open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"


# There is deliberately NO exception type here, unlike `tools/gates` and
# `tools/vocabulary`. Those compile a document and either return it or refuse;
# this sweep's whole output is a list of findings, so raising on the first one
# would throw away the report. Every entry point returns its faults, and the
# gate decides what to do with them.
