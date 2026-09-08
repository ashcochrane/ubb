"""What the costing read answers, asked directly (#320, #428).

`costing.cost_declaration` is the one read a rating path may make of the
catalogue (`apps/platform/tests/test_event_type_satellite_invariants.py`), and
until #428 it was exercised only through the compute spine's own cases. #428
gave it a fourth fact — WHICH quantity codes the declaration carries — and a
read that grows a fact is worth asking on its own, for two reasons the spine's
cases cannot cover:

* the read's own docstring promises **one query, and it stays one** on the
  hottest write path in the system, and nothing pinned that until now; and
* the fourth fact has an empty case and an absent case that look alike from
  the spine — a declaration carrying no quantities answers an empty set, and
  no declaration at all answers `None` — and the difference is the whole of
  the opt-in rule the join rests on.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.platform.event_types.costing import cost_declaration
from apps.platform.event_types.tests._helpers import declares_an_event_type
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    SOURCE_KIND_CALLER_SUPPLIED,
)

KEY = "acme.embed"


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _declaration(tenant, *, key=KEY, **facts):
    """`declares_an_event_type` with this module's key as the default."""
    return declares_an_event_type(tenant, key, **facts)


@pytest.mark.django_db
class TestWhichQuantitiesADeclarationCarries:
    """The fourth fact, and the two shapes the spine cannot tell apart."""

    def test_the_declared_codes_are_answered_as_a_set(self):
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "completion_tokens"))

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset(
            {"prompt_tokens", "completion_tokens"})

    def test_a_declaration_carrying_no_quantity_answers_an_empty_set(self):
        """Empty, and a set — not `None`, and not a set holding a null.

        A left join over a declaration with nothing beneath it produces one
        row with a null code, and an aggregate that kept it would answer
        `{None}`: a set with one member that is not a name, against which
        every real name would read as undeclared correctly and `None` would
        read as declared. The read strips it, and this is where that is held.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=())

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset()
        assert declaration.declares_no_cost

    def test_the_codes_are_the_declarations_own_and_not_the_tenants(self):
        """Declarations are Event-Type-local (#193 §C2), and so is this set.

        The same code beneath another Event Type of the same tenant is a
        different record, and a set that pooled the tenant's catalogue would
        make a name declared ANYWHERE read as declared HERE — which is the
        exact reading the quarantine link exists to refuse.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens",))
        _declaration(tenant, key="acme.rerank", quantities=("reasoning_tokens",))

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset({"prompt_tokens"})

    def test_no_declaration_is_none_and_not_an_empty_declaration(self):
        """The opt-in rule, at the read: absence is a different answer."""
        tenant = _tenant()
        _declaration(_tenant("Other"), quantities=("prompt_tokens",))

        assert cost_declaration(tenant=tenant, key=KEY) is None
        assert cost_declaration(tenant=tenant, key="") is None

    def test_the_other_three_facts_are_unmoved_by_the_fourth(self):
        """The count the no-cost rule reads is now derived from the set, so
        the set arriving must not have moved the rule."""
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True)

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.costing_method == COSTING_METHOD_REPORTED
        assert not declaration.declares_no_cost
        assert declaration.reported_cost_source_kind == \
            SOURCE_KIND_CALLER_SUPPLIED


@pytest.mark.django_db
class TestOneQueryAndItStaysOne:
    """The module's own promise, pinned — the read sits on the recording path."""

    def test_the_read_is_one_query_whatever_the_declaration_carries(self):
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "completion_tokens"),
                     mapping=True)

        with CaptureQueriesContext(connection) as queries:
            declaration = cost_declaration(tenant=tenant, key=KEY)

        assert len(queries) == 1, [q["sql"] for q in queries]
        assert declaration.declared_quantity_codes == frozenset(
            {"prompt_tokens", "completion_tokens"})
        assert declaration.reported_cost_source_kind == \
            SOURCE_KIND_CALLER_SUPPLIED

    def test_the_read_is_one_query_for_a_bare_declaration_too(self):
        tenant = _tenant()
        _declaration(tenant, quantities=())

        with CaptureQueriesContext(connection) as queries:
            cost_declaration(tenant=tenant, key=KEY)

        assert len(queries) == 1, [q["sql"] for q in queries]
