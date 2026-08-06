"""The reference readers: which generated names a consumer holds (#227).

The load-bearing half of G2 and G3. Everything here is about the ONE question
#191 decision 3 permits — *does this consumer reach the generated artifact by
name?* — and about the shapes in which the answer can hide.

No test in this module contains a registry VALUE. That is the acceptance
criterion stated as a property of the test file: if the census compared source
against value spellings, these tests could not be written without them.
"""

import pytest

from tools.consumers import errors as codes
from tools.consumers.references import (
    console_alias_roots,
    console_specifiers,
    python_references,
    resolve_alias_roots,
    typescript_references,
)

BACKEND = "core.vocabulary"
SDK = "ubb.vocabulary"
WHERE = "backend::example.py"


def names(text, module=BACKEND):
    found, faults = python_references(text, module, WHERE)
    assert not faults, faults
    return found


def _codes(faults):
    return {fault.code for fault in faults}


# ---------------------------------------------------------------------------
# Python: the backend and the SDK
# ---------------------------------------------------------------------------

def test_a_named_import_is_a_reference():
    assert names("from core.vocabulary import ALPHA, BETA\n") == {"ALPHA",
                                                                  "BETA"}


def test_a_renamed_import_is_read_as_the_artifacts_own_name():
    """What the consumer calls it locally is its own business.

    The name that matters is the one the generator bound, because that is the
    end of the reference. A consumer aliasing it has still stopped holding a
    second copy, which is the whole property under test.
    """
    assert names("from core.vocabulary import ALPHA as A\n") == {"ALPHA"}


def test_a_namespace_import_is_read_through_its_attributes():
    """The SDK's own docstring recommends exactly this spelling."""
    assert names("from ubb import vocabulary\n"
                 "x = vocabulary.ALPHA\n", module=SDK) == {"ALPHA"}


def test_a_dotted_import_with_an_alias_is_read_through_its_attributes():
    assert names("import core.vocabulary as v\nx = v.ALPHA\n") == {"ALPHA"}


def test_a_dotted_import_without_an_alias_is_read_through_the_full_chain():
    """`import core.vocabulary` binds `core`, so the attribute is two deep.

    Matching on the last segment alone would read `core.vocabulary.ALPHA` as a
    reference to `vocabulary`, and report a consumer that holds every value as
    one that holds none.
    """
    assert names("import core.vocabulary\n"
                 "x = core.vocabulary.ALPHA\n") == {"ALPHA"}


def test_a_relative_import_resolves_against_the_artifacts_package():
    """`from .vocabulary import X`, inside `ubb/` — the SDK's own spelling."""
    assert names("from .vocabulary import ALPHA\n", module=SDK) == {"ALPHA"}


def test_an_import_of_a_different_module_is_not_a_reference():
    assert names("from elsewhere.vocabulary import ALPHA\n") == set()
    assert names("from core.models import ALPHA\n") == set()


def test_a_function_body_import_is_a_reference():
    """The lazy import ADR-001's boundary walker exists to catch.

    A reference is a reference wherever it is written, and a census that only
    read module-level imports would report a served consumer as unserved for
    the whole of a slice.
    """
    assert names("def f():\n    from core.vocabulary import ALPHA\n"
                 "    return ALPHA\n") == {"ALPHA"}


def test_a_star_import_is_a_fault_rather_than_a_pass():
    """It puts every name in scope and says nothing about which are held.

    Counting it as "holds everything" would let one line excuse a whole
    surface — the inert-suppression shape this repository has shipped three
    times. Counting it as "holds nothing" would be a false debt. So it is
    neither: the census reports that it could not see.
    """
    found, faults = python_references("from core.vocabulary import *\n",
                                      BACKEND, WHERE)
    assert found == frozenset()
    assert _codes(faults) == {codes.STAR_IMPORT}


def test_unparseable_python_is_a_fault_rather_than_an_empty_answer():
    """"Read nothing" and "found nothing" are one output, and the second is how
    a gate goes green by doing nothing."""
    found, faults = python_references("def (:\n", BACKEND, WHERE)
    assert found == frozenset()
    assert _codes(faults) == {codes.CONSUMER_UNPARSEABLE}


def test_a_matching_string_literal_is_not_a_reference():
    """The acceptance criterion, as a control.

    A consumer that spells a value correctly and imports nothing holds nothing.
    This is the coincidence a literal scan cannot tell from agreement, and the
    reason the census never looks at one.
    """
    assert names('CHOICES = [("alpha", "Alpha"), ("beta", "Beta")]\n') == set()


# ---------------------------------------------------------------------------
# TypeScript: the console
# ---------------------------------------------------------------------------

SPECIFIERS = frozenset({"@/lib/vocabulary", "./vocabulary"})


def ts_names(text, specifiers=SPECIFIERS):
    found, faults = typescript_references(text, specifiers, "console::labels.ts")
    assert not faults, faults
    return found


def test_a_named_typescript_import_is_a_reference():
    assert ts_names('import { ALPHA, BETA } from "@/lib/vocabulary";\n') == {
        "ALPHA", "BETA"}


def test_a_type_only_import_is_a_reference():
    """A type import is how the console's own compiler enforces membership.

    Refusing to count it would report the strongest form of holding a value by
    reference as the absence of one.
    """
    assert ts_names('import type { Alpha } from "@/lib/vocabulary";\n') == {
        "Alpha"}
    assert ts_names('import { type Alpha, BETA } from "./vocabulary";\n') == {
        "Alpha", "BETA"}


def test_a_renamed_typescript_import_is_read_as_the_artifacts_own_name():
    assert ts_names('import { ALPHA as A } from "@/lib/vocabulary";\n') == {
        "ALPHA"}


def test_a_multiline_import_is_a_reference():
    """Prettier wraps a long import list, and every real one here is wrapped."""
    assert ts_names('import {\n  ALPHA,\n  BETA,\n} from "@/lib/vocabulary";\n'
                    ) == {"ALPHA", "BETA"}


def test_a_namespace_import_is_read_through_its_member_accesses():
    assert ts_names('import * as v from "@/lib/vocabulary";\n'
                    'const x = v.ALPHA;\n') == {"ALPHA"}


def test_an_import_from_elsewhere_is_not_a_reference():
    assert ts_names('import { ALPHA } from "@/lib/labels";\n') == set()


def test_a_typescript_re_export_is_a_fault_rather_than_a_pass():
    """Same reasoning as the Python star import, in the console's spelling."""
    found, faults = typescript_references('export * from "@/lib/vocabulary";\n',
                                          SPECIFIERS, "console::labels.ts")
    assert found == frozenset()
    assert _codes(faults) == {codes.STAR_IMPORT}


def test_a_matching_typescript_literal_is_not_a_reference():
    assert ts_names('export const X = ["alpha", "beta"] as const;\n') == set()


# ---------------------------------------------------------------------------
# Resolving the console's module specifiers
# ---------------------------------------------------------------------------

ALIAS_ROOTS = {"@/*": ("apps/ui/src/",)}


def test_the_alias_and_the_relative_path_both_resolve_to_the_artifact():
    """Both are legal spellings of one import, so both must be seen.

    Reading only the alias would report the artifact's own neighbour — the file
    most likely to import it — as holding nothing.
    """
    specifiers = console_specifiers("apps/ui/src/lib/labels.ts",
                                    "apps/ui/src/lib/vocabulary.ts",
                                    ALIAS_ROOTS)
    assert "@/lib/vocabulary" in specifiers
    assert "./vocabulary" in specifiers


def test_a_relative_specifier_climbs_out_of_a_nested_directory():
    specifiers = console_specifiers(
        "apps/ui/src/features/tasks/components/table.tsx",
        "apps/ui/src/lib/vocabulary.ts", ALIAS_ROOTS)
    assert "../../../lib/vocabulary" in specifiers


def test_the_alias_roots_come_from_the_consoles_own_tsconfig():
    """Derived, not restated. A second copy would go stale in silence — the
    census would stop seeing aliased imports and report every console consumer
    as holding nothing, which reads as a large new debt rather than as a bug."""
    paths, faults = console_alias_roots(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}',
        "apps/ui/tsconfig.json")
    assert not faults
    assert resolve_alias_roots(paths, "apps/ui") == {"@/*": ("apps/ui/src/",)}


@pytest.mark.parametrize("text, why", [
    ("{ not json", "unparseable"),
    ('{"compilerOptions": {}}', "no paths"),
    ("{}", "no compilerOptions"),
])
def test_an_unreadable_tsconfig_is_a_fault_rather_than_an_empty_alias_map(
        text, why):
    _, faults = console_alias_roots(text, "apps/ui/tsconfig.json")
    assert _codes(faults) == {codes.ALIAS_UNRESOLVED}, why
