"""The structured path grammar, the renderer and the advisory checker (#263).

No database and no model: the three claims here are about a path as a value, and
testing them through a row would only add a way for them to be true by accident.

The claims, in the order the ticket makes them:

* **The path is structured data, never a code expression.** A stored
  ``response.usage.input_tokens`` is Python source in a column, and the builder
  emits more than one language.
* **The renderer may change access syntax, and must never translate a field
  name.** This is the one that has money behind it: Google's REST response
  carries ``usageMetadata.promptTokenCount`` and its own Python SDK carries
  ``usage_metadata.prompt_token_count``, and a renderer that "helpfully" moved
  between them would be making UBB's catalogue commercially load-bearing.
* **The checker advises and never substitutes.** Proved by the strongest
  available form: the inputs are compared before and after, and the advisory
  text is required to carry the tenant's own spelling rather than a replacement.
"""
import pytest

from apps.platform.event_types.models import RECOGNISED_RESPONSE_SHAPES
from apps.platform.event_types.source_paths import (
    ACCESS_ATTRIBUTE,
    ACCESS_STYLES,
    ACCESS_SUBSCRIPT,
    CONVENTION_LOWER_CAMEL,
    CONVENTION_SNAKE,
    SHAPE_CONVENTIONS,
    SourcePathNotRenderable,
    advisories,
    path_errors,
    render,
)
from core.vocabulary import (
    SOURCE_SHAPE_ID_CUSTOM,
    SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
)

#: The trap, as the decision records it: one supplier, one number, two spellings.
REST_PATH = ["usageMetadata", "promptTokenCount"]
SDK_PATH = ["usage_metadata", "prompt_token_count"]


class TestThePathIsStructuredData:
    """A sequence of keys. Anything that composes them is code."""

    def test_a_list_of_keys_is_a_path(self):
        assert path_errors(SDK_PATH) == ()

    def test_an_empty_path_is_a_path(self):
        """A measurement that reads nothing from the response declares no path.

        Whether a path is REQUIRED is the source kind's question and is asked on
        the model; the grammar's job is only to say what a path is.
        """
        assert path_errors([]) == ()

    def test_a_code_expression_is_refused(self):
        """The headline refusal, in the spelling a developer would reach for."""
        errors = path_errors(["response.usage.input_tokens"])

        assert errors
        assert "expression" in errors[0]

    def test_a_subscript_expression_is_refused_too(self):
        """The same path in the other syntax is the same mistake."""
        errors = path_errors(['usage["input_tokens"]'])

        assert errors
        assert "expression" in errors[0]

    def test_a_call_is_refused(self):
        assert path_errors(["get_usage()"])

    def test_a_bare_string_is_not_a_path(self):
        """The likeliest wrong shape of all: the whole path as one string.

        A string is a sequence, so a check that only asked for "a sequence of
        strings" would read `"ab"` as the two segments `a` and `b` and pass.
        """
        errors = path_errors("usage_metadata.prompt_token_count")

        assert errors
        assert "list of segments" in errors[0]

    def test_a_non_string_segment_is_refused(self):
        assert path_errors(["candidates", 0])

    def test_an_empty_segment_is_refused(self):
        """A step that reads nothing is a step missing, not the whole response."""
        assert path_errors(["usage", ""])

    def test_every_bad_segment_is_reported_not_only_the_first(self):
        """One pass, so a tenant fixing a path is not told about it twice."""
        assert len(path_errors(["a.b", "c[0]"])) == 2

    def test_a_backslash_is_refused(self):
        """It is what quoting is made of, so it composes exactly as a quote does.

        A segment ending in one escapes the closing quote of the string it is
        rendered into, and emission runs on into the next line of a tenant's
        generated integration.
        """
        assert path_errors(["a\\b"])
        assert path_errors(["trailing\\"])

    def test_a_control_character_is_refused(self):
        """A newline inside a key is not a key anybody typed.

        Nobody composes with one, so it is not an expression character — but it
        ends the LINE of generated code the segment goes into, which is the same
        harm arriving by a different door.
        """
        assert path_errors(["a\nb"])
        assert path_errors(["a\tb"])
        assert path_errors(["a\x00b"])

    def test_a_supplier_key_ubb_would_not_have_chosen_is_accepted(self):
        """UBB does not impose a charset on a supplier's own field names.

        `x-request-id` is a real key, and refusing it would be UBB deciding what
        a supplier may call its own fields — the same objection that made the
        catalogue's keys plain character fields rather than slugs.
        """
        assert path_errors(["headers", "x-request-id"]) == ()


class TestTheRendererMayChangeSyntax:
    """Both styles, one path — that is the whole permission."""

    def test_attribute_access(self):
        assert render(SDK_PATH, ACCESS_ATTRIBUTE) == (
            "response.usage_metadata.prompt_token_count")

    def test_subscript_access(self):
        assert render(SDK_PATH, ACCESS_SUBSCRIPT) == (
            'response["usage_metadata"]["prompt_token_count"]')

    def test_the_root_is_the_targets_business(self):
        assert render(["total"], ACCESS_ATTRIBUTE, root="payload") == (
            "payload.total")

    def test_an_unknown_style_is_refused_rather_than_guessed(self):
        with pytest.raises(ValueError):
            render(SDK_PATH, "javascript")


class TestTheRendererNeverTranslatesAFieldName:
    """The rule with money behind it, checked over every style and every path."""

    @pytest.mark.parametrize("access", ACCESS_STYLES)
    @pytest.mark.parametrize("segments", [SDK_PATH, REST_PATH, ["total"]])
    def test_every_segment_appears_exactly_as_declared(self, access, segments):
        rendered = render(segments, access)

        for segment in segments:
            assert segment in rendered, (
                f"{segment!r} did not survive rendering into {access} access")

    def test_the_two_spellings_stay_two_paths(self):
        """The trap, stated as an assertion.

        Same supplier, same number, two clients, two names. If any rendering of
        the REST path ever produced the SDK path, UBB would be renaming a
        supplier's field — and it would be doing it inside generated code that a
        tenant deploys and bills against.
        """
        for access in ACCESS_STYLES:
            assert render(REST_PATH, access) != render(SDK_PATH, access)

    def test_a_path_that_cannot_be_reached_by_attribute_is_refused_not_mangled(self):
        """`x-request-id` is not an attribute in any target this builder emits.

        The ways round this are all renames — drop the hyphens, camel-case it,
        guess at an accessor the supplier might also offer — so the answer is to
        refuse the style and say which one works, per #156 §5.4: the builder
        does not emit plausible-looking code.
        """
        with pytest.raises(SourcePathNotRenderable) as refused:
            render(["headers", "x-request-id"], ACCESS_ATTRIBUTE)

        assert ACCESS_SUBSCRIPT in str(refused.value)

    def test_the_same_path_renders_under_the_style_that_can_express_it(self):
        """The other half: refusing a style is not refusing the path."""
        assert render(["headers", "x-request-id"], ACCESS_SUBSCRIPT) == (
            'response["headers"]["x-request-id"]')

    @pytest.mark.parametrize("access", ACCESS_STYLES)
    @pytest.mark.parametrize("segment", ['a"b', "a\\b", "trailing\\", "a\nb",
                                         "usage.tokens"])
    def test_a_segment_that_is_not_a_key_is_never_emitted(self, access, segment):
        """The renderer re-asks the grammar, and that is not belt-and-braces.

        `clean()` is a courtesy to the ordinary path (ADR-0007 §2) — a
        `create()` or an `update()` that skips validation goes round it, as it
        goes round every model-level guard here. The other guards defend a
        column; this one defends the moment the value becomes code in a tenant's
        repository, which is the only place the harm can actually happen. Each
        segment below would otherwise have closed, escaped or ended the string
        literal it was rendered into and left the emitted line running on.
        """
        with pytest.raises(SourcePathNotRenderable):
            render([segment], access)


class TestTheCheckerAdvisesAndNeverSubstitutes:
    """Advice is the product. A quiet rewrite is the failure being designed out."""

    def test_a_rest_path_under_an_sdk_shape_is_advised(self):
        found = advisories(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1, REST_PATH)

        assert len(found) == 2
        assert CONVENTION_SNAKE in found[0]

    def test_an_sdk_path_under_a_rest_shape_is_advised(self):
        """Checked in both directions: neither convention is the default."""
        found = advisories(SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1, SDK_PATH)

        assert len(found) == 2
        assert CONVENTION_LOWER_CAMEL in found[0]

    def test_a_consistent_path_draws_no_advice(self):
        """The positive control. Advice on everything is advice on nothing."""
        assert advisories(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1, SDK_PATH) == ()
        assert advisories(SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1, REST_PATH) == ()

    def test_the_advice_carries_the_tenants_own_spelling_and_no_other(self):
        """The substitution check, at the one place a replacement could hide.

        A checker that "advised" by naming the corrected spelling would have
        done the rename — in prose rather than in a column, and a tenant would
        paste it back. So the advisory is required to quote what was declared,
        and required not to contain what UBB would have written instead.
        """
        found = advisories(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
                           ["promptTokenCount"])

        assert "promptTokenCount" in found[0]
        assert "prompt_token_count" not in found[0]

    def test_the_declared_path_is_not_touched(self):
        """The other half of never-substitutes: the input is left alone."""
        declared = list(REST_PATH)
        advisories(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1, declared)

        assert declared == REST_PATH

    def test_a_tenants_own_wrapper_draws_no_advice(self):
        """`custom` names a shape UBB does not know, so UBB validates nothing."""
        assert advisories(SOURCE_SHAPE_ID_CUSTOM, REST_PATH) == ()
        assert advisories("", REST_PATH) == ()
        assert advisories("acme.wrapper.v2", REST_PATH) == ()

    def test_a_single_lowercase_word_draws_no_advice_under_either_shape(self):
        """Most keys have no opinion, and an advisory that fired on them
        would be switched off within a week."""
        assert advisories(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1, ["usage"]) == ()
        assert advisories(SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1, ["usage"]) == ()

    def test_every_shape_ubb_recognises_has_something_to_say_about_it(self):
        """The coverage guard, and it is meant to go red.

        A shape UBB recognises but has no convention for is a shape whose paths
        are silently unchecked — the advisory would simply never fire and
        nothing would say so. When the registry learns a fourth shape, this
        fails and the convention is declared with it.
        """
        assert set(SHAPE_CONVENTIONS) == set(RECOGNISED_RESPONSE_SHAPES), (
            "a response shape UBB recognises has no declared field-naming "
            "convention, so the advisory checker is silent about every path "
            "declared against it")
