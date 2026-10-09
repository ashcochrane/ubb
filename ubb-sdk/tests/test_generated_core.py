"""Ratchet pins for the generated transport+DTO core (issue #84).

These are behaviour tests, not shape tests: they pin the *guarantees* the wrap
makes about the generated core — open-world tolerance, required-where-true
typing, and the spec-revision stamp — rather than the hand-typed field list of
any one DTO (that job moved to the generator + the CI regeneration gate).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ubb._core.models.record_usage_response import RecordUsageResponse
from ubb._core.models.problem_out import ProblemOut
from ubb._core.models.usage_batch_item_response import UsageBatchItemResponse
from ubb._core.types import UNSET, Unset

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_SPEC = REPO_ROOT / "openapi" / "v1.json"

# What a recording acknowledgement says about a stop beyond its verdict (#569).
# Every acknowledgement carries all three; null is "does not apply".
STOP_FACTS = ("trigger_source", "stop_bound_micros", "stop_measured_micros")
NOTHING_STOPPED = dict.fromkeys(STOP_FACTS)


class TestOpenWorldFieldTolerance:
    """A pinned client never crashes on a field it was not generated to know."""

    def test_unknown_field_lands_in_additional_properties(self):
        r = RecordUsageResponse.from_dict(
            {
                "event_id": "evt_1",
                "suspended": False,
                "costing_status": "known", "pricing_status": "known",
                **NOTHING_STOPPED,
                # A field added to the response after this client was pinned:
                "brand_new_field": {"nested": 1},
            }
        )
        assert r.event_id == "evt_1"
        assert r.additional_properties["brand_new_field"] == {"nested": 1}

    def test_problem_extension_members_are_open(self):
        # RFC 9457 extension members (e.g. balance_micros on an insufficient
        # balance) are deliberately unmodeled and must round-trip untouched.
        p = ProblemOut.from_dict(
            {
                "type": "about:blank",
                "title": "Insufficient balance",
                "status": 409,
                "code": "insufficient_balance",
                "balance_micros": -500,
            }
        )
        assert p.code == "insufficient_balance"
        assert p["balance_micros"] == -500


class TestOpenEnumTolerance:
    """Response enums are bare strings in the contract (ADR-003 open enums), so a
    value minted after this client was pinned parses as a plain str, never a
    crash or a dropped field."""

    def test_novel_stop_scope_value_survives(self):
        r = RecordUsageResponse.from_dict(
            {
                "event_id": "evt_1",
                "suspended": False,
                "costing_status": "known", "pricing_status": "known",
                **NOTHING_STOPPED,
                "stop": True,
                "stop_scope": "a_scope_invented_next_year",
            }
        )
        assert r.stop is True
        assert r.stop_scope == "a_scope_invented_next_year"


class TestRequiredWhereTrueTyping:
    """The spec's presence promises flow into the generated types: a
    required-in-the-contract field is required in the model (no UNSET/None
    default), an optional one defaults to UNSET."""

    def test_required_field_has_no_default(self):
        with pytest.raises(TypeError):
            # event_id / suspended / costing_status are required. The third
            # joined them in #317: a supplier cost with no statement about
            # whether it is settled is the ambiguity that ticket removed, so
            # the contract does not let one arrive.
            RecordUsageResponse()
        with pytest.raises(KeyError):
            RecordUsageResponse.from_dict({"suspended": False})  # missing event_id

    def test_optional_field_defaults_to_unset(self):
        r = RecordUsageResponse.from_dict(
            {"event_id": "evt_1", "suspended": False, "costing_status": "known", "pricing_status": "known",
             **NOTHING_STOPPED})
        assert isinstance(r.task_id, Unset)
        assert r.task_id is UNSET

    @pytest.mark.parametrize("model, body", [
        (RecordUsageResponse,
         {"event_id": "evt_1", "suspended": False, "costing_status": "known", "pricing_status": "known"}),
        # A rejected batch item recorded nothing, and carries the three as null.
        (UsageBatchItemResponse,
         {"accepted": False, "code": "validation_error", "detail": "refused", "stop": False}),
    ])
    def test_a_stop_fact_is_a_required_key_whose_value_may_be_null(self, model, body):
        # The owner's review of #612: the three are REQUIRED AND NULLABLE.
        # Null says "this fact does not apply"; a missing key would be a third
        # state — the server not sending what it promised — so the generated
        # model refuses a body without one rather than defaulting it to UNSET.
        parsed = model.from_dict({**body, **NOTHING_STOPPED})
        for fact in STOP_FACTS:
            assert getattr(parsed, fact) is None
        for missing in STOP_FACTS:
            without = {**body, **{f: None for f in STOP_FACTS if f != missing}}
            with pytest.raises(KeyError, match=missing):
                model.from_dict(without)


class TestSpecRevisionStamp:
    """Each SDK build is tied to the exact committed spec it was generated from."""

    def test_stamp_matches_committed_spec(self):
        from ubb import _spec_revision

        expected = hashlib.sha256(COMMITTED_SPEC.read_bytes()).hexdigest()
        assert _spec_revision.SPEC_SHA256 == expected
        assert _spec_revision.GENERATOR == "openapi-python-client"
        assert _spec_revision.GENERATOR_VERSION == "0.29.0"

    def test_stamp_version_matches_spec_document(self):
        from ubb import _spec_revision

        doc_version = json.loads(COMMITTED_SPEC.read_bytes())["info"]["version"]
        assert _spec_revision.SPEC_VERSION == doc_version
