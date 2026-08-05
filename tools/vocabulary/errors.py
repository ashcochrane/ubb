"""The named reasons a registry can be invalid.

Every failure the compiler reports carries one of the codes below. They are
module constants rather than inline strings for one reason: a test asserts on
the code, so a reworded message never silently turns a negative control into a
test that passes for the wrong reason.
"""

from dataclasses import dataclass

# --- Structure: the registry directory and the files in it -----------------
REGISTRY_MISSING = "registry_missing"          # the directory or a required file is absent
REGISTRY_EMPTY = "registry_empty"              # concepts/ holds no .yaml files
UNEXPECTED_FILE = "unexpected_file"            # something in concepts/ that is not a .yaml file
YAML_INVALID = "yaml_invalid"                  # the file does not parse
DUPLICATE_KEY = "duplicate_key"                # the same key twice in one mapping
FILE_NOT_MAPPING = "file_not_mapping"          # a domain file is not a mapping of concepts
CONCEPT_NOT_MAPPING = "concept_not_mapping"    # a concept body is not a mapping

# --- The schema itself ------------------------------------------------------
SCHEMA_INVALID = "schema_invalid"              # schema.yaml does not describe a usable schema
CONSUMERS_INVALID = "consumers_invalid"        # consumers.yaml does not declare usable surfaces
SURFACE_ROOT_MISSING = "surface_root_missing"  # a declared surface's root is not in the repo

# --- Concept shape ----------------------------------------------------------
UNKNOWN_KIND = "unknown_kind"                  # a kind the schema does not declare
MISSING_FIELD = "missing_field"                # a field this kind requires
FORBIDDEN_FIELD = "forbidden_field"            # a field this kind forbids
UNKNOWN_FIELD = "unknown_field"                # a field the schema declares nowhere
INVALID_FIELD_TYPE = "invalid_field_type"      # a field present but the wrong shape or blank
INVALID_TOKEN = "invalid_token"                # a name or value outside the token pattern
INVALID_TOKEN_PATTERN = "invalid_token_pattern"  # a per-concept override that is not a regex
EMPTY_VALUE_SET = "empty_value_set"            # a closed/open concept declaring no values
DUPLICATE_VALUE = "duplicate_value"            # the same value twice in one concept
OPEN_MUST_ALLOW_UNKNOWN = "open_must_allow_unknown"  # `open` with allow_unknown not true
RETIRED_ALIAS_COLLISION = "retired_alias_collision"  # a retired term that is also live
DUPLICATE_RETIRED_ALIAS = "duplicate_retired_alias"  # one term retired by two concepts

# --- Identity across files --------------------------------------------------
DUPLICATE_TERM = "duplicate_term"              # the same concept, defined twice
CONFLICTING_DEFINITION = "conflicting_definition"  # ... and the two definitions disagree

# --- Declared consumers -----------------------------------------------------
CONSUMER_NOT_MAPPING = "consumer_not_mapping"          # an entry that is not {surface, path}
UNKNOWN_CONSUMER_SURFACE = "unknown_consumer_surface"  # a surface consumers.yaml does not declare
CONSUMER_PATH_MISSING = "consumer_path_missing"        # a path that does not exist in the repo
CONSUMER_PATH_OUTSIDE_SURFACE = "consumer_path_outside_surface"  # a path outside its surface's root


@dataclass(frozen=True, order=True)
class RegistryError:
    """One reason a registry is invalid.

    ``location`` names the file and, where there is one, the concept — enough
    for a reader to open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"


class RegistryInvalid(Exception):
    """Raised with EVERY error found, not just the first.

    A registry with four mistakes should take one run to fix, not four.
    """

    def __init__(self, errors):
        self.errors = tuple(sorted(errors))
        super().__init__(
            f"{len(self.errors)} registry error(s):\n"
            + "\n".join(f"  {error}" for error in self.errors)
        )

    def codes(self):
        """The set of codes reported — what negative controls assert on."""
        return {error.code for error in self.errors}
