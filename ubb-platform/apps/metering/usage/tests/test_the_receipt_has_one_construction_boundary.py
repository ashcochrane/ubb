"""A receipt reaches the column through one function, and holds values (#349).

Three claims, and they need three different kinds of check.

**There is one construction site and one writer.** That is a claim about the
tree, so it is a walk over the tree — the shape `test_no_bare_supplier_cost_
aggregate.py` uses for the same reason: fifteen call sites repaired by hand stop
nothing from the sixteenth being written next week in the shape that reads
perfectly. Both expectations are declared as {module: COUNT}, never as a set of
module names, and that distinction was measured rather than reasoned about — see
the comment on `BUILDS_A_RECEIPT`, where the set form is the vacuous one.

⚠ **What the walk does not cover, said out loud.** It reads the name a keyword
argument or an attribute assignment is written under, plus the one other
spelling a writer can use — a mapping keyed on `Posting.RECEIPT_COLUMN`, which
is how every module outside the recording path has to address the column,
because the column's name is retired and the ratchet caps how many files may say
it. A receipt persisted through `setattr` with a computed name, or by raw SQL,
still passes. That is honest about being a tripwire for the spellings writers
actually use. The behavioural half below is what covers the recording path
itself, and the database-level rule — a field recorded as unresolved completing
exactly once — is a separate decision proved through three doors.

⚠ **THE CONSTANT-ADDRESSED SPELLING WAS ADDED BECAUSE A WRITER ARRIVED IN IT
(#363).** The two doors that complete a posting — a supplier cost, a customer
price — write the receipt in the same statement as the columns, and neither may
spell the column literally. Before this, the walk read the literal keyword only,
so both would have been invisible: a gate that cannot see the spelling every new
writer must use is a gate that goes quiet exactly when a writer arrives.

**Every receipt that reaches the column validates.** That is behaviour, so it is
recorded through the service and read back off the row. It is the check that
survives a second writer being added: a hand-built record that is not a receipt
fails here even if the walk above were somehow satisfied.

**The values are the authority.** So the configuration that produced an amount
is EDITED after the fact and the stored record is asked again. Nothing may move
— not the totals, not the components — and the ids the record does carry are
cross-references that no read path follows for a figure.

This module never spells the column: `Posting.RECEIPT_COLUMN` is what addresses
it. That was written while the column carried the retired spelling of the
concept, and #370 is the day it paid — the rename landed and the walk came with
it, instead of going quietly vacuous over a column nothing was called any more.
"""
import ast
from pathlib import Path

import pytest

from apps.metering.pricing.receipts import (
    RECEIPT_SCHEMA_VERSION, uncosted_quantity_keys, validate_receipt,
)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
)

# apps/metering/usage/tests/<this file> -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[4]

SEARCH_ROOTS = ("apps", "api", "core")
SKIP_PARTS = ("tests", "migrations", "conformance")

#: THE ONE PLACE A RECEIPT IS BUILT.
CONSTRUCTOR = "build_receipt"

#: Where a receipt is built, and how many times. The engine that resolves an
#: amount is the thing that can explain it, so this is the compute spine and
#: nothing else — and it builds ONE, at the foot of the one method that decides
#: both statuses.
#:
#: ⚠ A COUNT AND NOT A BARE NAME, and this was measured rather than assumed: the
#: same declaration written as a set of modules stayed GREEN under a mutation
#: that added a second construction site inside the permitted file. "One place a
#: receipt is built" is a claim about call sites, and a set of paths cannot make
#: it — it says only that no OTHER module builds one, which is the easier half.
BUILDS_A_RECEIPT = {"apps/metering/pricing/services/pricing_service.py": 1}

#: Where one is written to the column, and how many times — same reasoning. The
#: recording path inserts exactly one receipt per posting, and each of the two
#: completion doors writes one: the statement that settles a supplier cost and
#: the statement that resolves a customer price each carry the section they
#: completed, so the record and the columns beside it move together and cannot
#: come to disagree (#363).
#:
#: ⚠ THREE WRITERS IS NOT THREE BOUNDARIES. None of them builds a record: the
#: recording path persists what `build_receipt` returned, and each door persists
#: what `completed_receipt` returned from the record already on the row. The
#: claim this pair of expectations makes together is that a receipt is
#: constructed in one place and only ever persisted from there.
WRITES_THE_RECEIPT = {
    "apps/metering/usage/services/usage_service.py": 1,
    "apps/metering/pricing/services/cost_settlement.py": 1,
    "apps/metering/pricing/services/price_resolution.py": 1,
}

#: The name of the constant a module addresses the column through. Its NAME and
#: not its value: this file may not spell the column, and what the walk looks
#: for is the reference rather than the string it resolves to.
COLUMN_CONSTANT = "RECEIPT_COLUMN"


def _keyed_on_the_column(node):
    """A mapping literal with the receipt column's constant as a key.

    The write-position spelling available to a module that may not say the
    column's retired name — `**{Posting.RECEIPT_COLUMN: record}` inside an
    `update()`, which is a `**` expansion and therefore not a keyword the walk
    below could see any other way. A READER spells it
    `getattr(posting, Posting.RECEIPT_COLUMN)`, which is not a mapping key and
    is not a finding.
    """
    return isinstance(node, ast.Dict) and any(
        isinstance(key, ast.Attribute) and key.attr == COLUMN_CONSTANT
        for key in node.keys)


#: THE VERBS THAT PUT A ROW ON DISK, which a keyword argument named after the
#: column has to be one of before it is a write (#370).
#:
#: ⚠ **THIS QUALIFIER WAS NOT NEEDED WHILE THE COLUMN CARRIED ITS RETIRED
#: SPELLING, AND THAT IS WHY IT IS HERE NOW.** The walk used to count ANY call
#: keyword spelled like the column, on the tacit premise that nothing else in
#: the tree was called that. #370 made the column's name the ratified name of
#: the record it holds — which is the right name for that value everywhere it
#: travels, so the tree now has three honest non-writes spelled exactly like a
#: write: `Costing(pricing_receipt=…)` on the compute spine's own record, and
#: the two settlement doors' `pricing_receipt=` parameter, which those doors
#: take a receipt through and decide for themselves whether to persist.
#:
#: The premise is RE-ESTABLISHED rather than the assertion weakened: a keyword
#: still counts wherever the call is an ORM write, and the positive control
#: below still fires on the spelling this walk exists for. The other two arms —
#: an attribute assignment and a mapping keyed on the constant — are not
#: qualified at all, because neither has a non-writing form.
#:
#: STATED RESIDUAL: a writer using a verb that is not in this set is not seen by
#: THIS arm. It is a whitelist and it is meant to be read as one; the two
#: unqualified arms are what stop that being the whole of the walk.
ORM_WRITES = frozenset({
    "create", "update", "bulk_create", "bulk_update",
    "get_or_create", "update_or_create", "save",
})


def _writes_a_row(call):
    """Whether this call puts a row on disk, or builds the row that will be.

    Two shapes, and the second is not an afterthought. `Posting.objects.create(…)`
    and `Posting.objects.filter(…).update(…)` end in one of the verbs above.
    `Posting(…)` ends in no verb at all — the model constructor, followed by a
    `.save()` that names no column — and it is the commonest Django write idiom
    there is. A first draft of this qualifier required an attribute call and lost
    that shape, which the unqualified arms do not cover either: it was counted
    before #370 and would have stopped being counted, in the commit whose whole
    subject is that the walk still finds every writer.

    Constructing a `Posting` is counted whether or not the object is saved.
    That over-reports by exactly the unsaved case, which is the safe direction:
    an over-report is a red gate a reader resolves, and no production path builds
    a posting carrying a receipt and then throws it away.

    `settle_provider_cost(…)` and `Costing(…)` are neither shape. The second is
    why the model is named rather than any constructor accepted — the compute
    spine's own result record takes the receipt under the same keyword, and it
    persists nothing.
    """
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in ORM_WRITES
    return isinstance(func, ast.Name) and func.id == Posting.__name__


def _sites(source):
    """Where one module builds a receipt, and where it writes one."""
    built, written = [], []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else getattr(func, "id", None))
            if name == CONSTRUCTOR:
                built.append(node.lineno)
            for keyword in node.keywords:
                if keyword.arg == Posting.RECEIPT_COLUMN and _writes_a_row(node):
                    written.append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Attribute)
                        and target.attr == Posting.RECEIPT_COLUMN):
                    written.append(node.lineno)
        elif _keyed_on_the_column(node):
            written.append(node.lineno)
    return built, written


def test_the_walk_sees_every_spelling_a_writer_uses():
    """The vacuity guard, one arm per spelling, through the real helper.

    Without it, a detector that had quietly stopped matching — a renamed
    constant, an `ast` shape that no longer occurs — would report a clean tree
    for a repository it never read. The third arm is the one that matters most
    here: it is a POSITIVE control for a spelling that produced no finding at
    all before #363, in a file that is not the one under test.
    """
    literal = f"Posting.objects.create({Posting.RECEIPT_COLUMN}=record)\n"
    assert _sites(literal)[1] == [1]

    assigned = f"posting.{Posting.RECEIPT_COLUMN} = record\n"
    assert _sites(assigned)[1] == [1]

    through_the_constant = "rows.update(**{Posting.RECEIPT_COLUMN: record})\n"
    assert _sites(through_the_constant)[1] == [1]

    # And a READ through the same constant is not a write.
    read = "stored = getattr(posting, Posting.RECEIPT_COLUMN)\n"
    assert _sites(read)[1] == []

    # ⚠ NOR IS HANDING THE SAME VALUE TO A FUNCTION (#370). The column's name is
    # now the record's name, so an ordinary call may legitimately take a
    # parameter spelled exactly like the column — the two settlement doors do,
    # and so does the compute spine's own result record. Each of these WOULD
    # have been counted before the qualifier, and each is a caller rather than a
    # writer: what persists the receipt is the door's own `update()`, which the
    # mapping arm above sees. This is the arm that makes `ORM_WRITES`
    # load-bearing rather than decorative.
    for not_a_write in (
            f"settle_provider_cost(posting_id=p, {Posting.RECEIPT_COLUMN}=r)\n",
            f"Costing({Posting.RECEIPT_COLUMN}=r)\n"):
        assert _sites(not_a_write)[1] == [], not_a_write

    # And the qualifier does not cost the walk a queryset write whose model is
    # not spelled at the call — the verb is what is checked, not the receiver.
    through_a_queryset = f"rows.update({Posting.RECEIPT_COLUMN}=record)\n"
    assert _sites(through_a_queryset)[1] == [1]

    # ⚠ NOR THE MODEL CONSTRUCTOR, WHICH ENDS IN NO VERB AT ALL and is the
    # commonest Django write idiom. This arm is here because the first draft of
    # the qualifier above required an attribute call and silently dropped it —
    # a shape the walk caught before #370, going uncaught in the commit whose
    # subject is that the walk still finds every writer. It is the pair with
    # `Costing(...)` two lines up that makes the discrimination real: both are
    # bare-name calls taking the same keyword, and only one of them is a row.
    built_then_saved = f"{Posting.__name__}({Posting.RECEIPT_COLUMN}=record)\n"
    assert _sites(built_then_saved)[1] == [1]


def _walk():
    for root in SEARCH_ROOTS:
        for path in sorted((PLATFORM_ROOT / root).rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield (path.relative_to(PLATFORM_ROOT).as_posix(),
                   _sites(path.read_text(encoding="utf-8")))


def test_exactly_one_place_builds_a_receipt():
    found = {path: len(built) for path, (built, _) in _walk() if built}

    assert found == BUILDS_A_RECEIPT, (
        f"A receipt is built in ONE place, and that place is where it is "
        f"validated — a second call site is a second boundary whether or not "
        f"it is in a second file. Found: {found}")


def test_no_production_path_persists_a_receipt_it_did_not_build():
    found = {path: len(written) for path, (_, written) in _walk() if written}

    assert found == WRITES_THE_RECEIPT, (
        f"The receipt column is written by the recording path alone, from the "
        f"value {CONSTRUCTOR} returned. A second writer either builds its own "
        f"record — which the one boundary exists to prevent — or repeats this "
        f"one. Found: {found}")


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


@pytest.mark.django_db
class TestWhatReachesTheColumn:
    def test_a_recorded_posting_carries_a_receipt_that_validates(self):
        tenant, customer = _tenant_and_customer()
        cost_rate_in_default_book(
            tenant, measurement_key="input_tokens",
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)

        result = UsageService.record_usage(
            tenant, customer, "k1",
            measurements={"input_tokens": 1_000})
        stored = getattr(Posting.objects.get(id=result["event_id"]),
                         Posting.RECEIPT_COLUMN)

        validate_receipt(stored)
        assert stored["receipt_schema_version"] == RECEIPT_SCHEMA_VERSION
        assert stored["subject_type"] == PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT
        assert stored["subject_id"] == str(result["event_id"])
        assert stored["currency"] == tenant.default_currency
        assert stored["costing"]["status"] == COSTING_STATUS_KNOWN
        assert stored["costing"]["method"] == COSTING_METHOD_CALCULATED

    def test_the_receipt_names_the_row_it_explains_and_not_another(self):
        """The subject is an input to resolution, so it is the row's own id —
        not whichever id happened to be in scope."""
        tenant, customer = _tenant_and_customer()

        first = UsageService.record_usage(tenant, customer, "k1")
        second = UsageService.record_usage(tenant, customer, "k2")
        receipts = [getattr(Posting.objects.get(id=r["event_id"]),
                            Posting.RECEIPT_COLUMN) for r in (first, second)]

        assert [r["subject_id"] for r in receipts] == [
            str(first["event_id"]), str(second["event_id"])]

    def test_a_row_in_the_older_shape_is_read_back_exactly_as_written(self):
        """Historical receipts are READ, never rewritten.

        No production path produces this shape any more, so a row built through
        the recording service would be asserting about a record the service
        cannot write. What this stands in for is **a row already on disk**, and
        it is now written the only way a row gets onto disk: at insert.

        ⚠ It was an `UPDATE` until #353, and that stopped being available on the
        commit that made this sentence true at the database rather than merely
        intended. The receipt's sealing rule is a `BEFORE UPDATE` trigger, and a
        record in a shape with no sections to complete has no move it admits —
        so the setup that stood in for "already on disk" was the exact statement
        the rule now refuses. That is #318's lesson a third time: installing a
        trigger takes `UPDATE` away as a setup technique, and the repair is to
        move the setup to `INSERT`, which the rule does not fire on and which is
        what the sentence above always meant.

        The row carries only what this test reads. Every column it leaves out
        takes the model's own empty value, which is the shape
        `tests/_helpers.py::committed_posting` already uses for a posting stood
        up to be read rather than to be recorded.
        """
        tenant, customer = _tenant_and_customer()
        older = {"engine_version": "2.1.0",
                 "uncosted_measurement_keys": ["image_pixels"],
                 "provider_cost_micros": 4_000, "billed_cost_micros": 4_800}

        posting = Posting.objects.create(
            tenant=tenant, customer=customer, idempotency_key="k-old",
            **{Posting.RECEIPT_COLUMN: older})
        stored = getattr(Posting.objects.get(id=posting.id),
                         Posting.RECEIPT_COLUMN)

        assert stored == older
        assert uncosted_quantity_keys(stored) == ["image_pixels"]


@pytest.mark.django_db
class TestTheValuesAreTheAuthority:
    def _record_against_a_price_rate(self):
        tenant, customer = _tenant_and_customer()
        rate = rate_in_default_book(
            tenant, measurement_key="input_tokens",
            rate_per_unit_micros=10_000, unit_quantity=1_000_000)
        result = UsageService.record_usage(
            tenant, customer, "k1",
            measurements={"input_tokens": 1_000_000})
        return result, rate

    def test_a_receipt_still_explains_its_amount_after_the_rule_is_edited(self):
        """The failure the whole pricing-versions decision exists to prevent:
        re-resolving a historical event against today's configuration answering
        a different number from the one the tenant was charged. The record holds
        values, so editing the rule moves nothing in it."""
        result, rate = self._record_against_a_price_rate()
        posting = Posting.objects.get(id=result["event_id"])
        before = getattr(posting, Posting.RECEIPT_COLUMN)
        assert before["totals"]["billed_cost_micros"] == 10_000
        assert before["pricing"]["method"] == PRICING_METHOD_DIRECT_EVENT_PRICE
        components = before["pricing"]["detail"]["components"]
        assert [line["micros"] for line in components] == [10_000]

        rate.rate_per_unit_micros = 999_000
        rate.save()

        posting.refresh_from_db()
        assert getattr(posting, Posting.RECEIPT_COLUMN) == before

    def test_no_read_path_reconstructs_an_amount_from_a_provenance_id(self):
        """The ids ride along and nothing follows them for a figure.

        Asserted on the RECORD rather than through a helper: the amounts a
        reader gets are the ones stored under `totals`, and a check that went
        through a function written for this test would be asserting about the
        test's own reader instead of about what anybody reads.
        """
        result, rate = self._record_against_a_price_rate()
        posting = Posting.objects.get(id=result["event_id"])
        stored = getattr(posting, Posting.RECEIPT_COLUMN)
        assert stored["provenance"]["price_rate_ids"] == {
            "input_tokens": str(rate.id)}
        before = stored["totals"]

        rate.rate_per_unit_micros = 999_000
        rate.save()

        posting.refresh_from_db()
        assert getattr(posting, Posting.RECEIPT_COLUMN)["totals"] == before

    def test_provenance_holds_ids_and_no_figures_at_all(self):
        result, _ = self._record_against_a_price_rate()
        stored = getattr(Posting.objects.get(id=result["event_id"]),
                         Posting.RECEIPT_COLUMN)

        for name, ids in stored["provenance"].items():
            assert all(isinstance(value, str) for value in ids.values()), name
