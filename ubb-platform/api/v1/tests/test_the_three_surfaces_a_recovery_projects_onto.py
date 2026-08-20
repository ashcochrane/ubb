"""The three read surfaces a Resolution Run projects onto, at the tenant
surface (#364, spec §10 ruling 12c and §24; user stories 34, 40 and 42).

The half a tenant actually touches. What each class holds:

* *Three reads and no fourth verb* — every one of them a GET, enumerated from
  the live API rather than from the routes this author remembered, because the
  claim "no money moves" is about the SURFACE and not about three handlers.
* *The declared rows name their counts* — asserted against the published
  schemas by name, because a `Schema` that does not name a key does not omit
  it, django-ninja DROPS it: the only surface a drift gate can see is the only
  one that can lose the field.
* *`unknown` never crosses as a currency amount* — walked over the whole
  response body rather than over the two fields a reader would check.
* *The receipts are reachable* — the path the projection publishes in its own
  prose is a route that exists, which nothing else type-checks.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The recording path's
correlation key is hidden behind `pricing/tests/_helpers`, and no book is
constructed here.
"""
import json

from django.test import Client, TestCase

from api.v1 import schemas
from api.v1.api import api
from apps.metering.pricing.tests._helpers import (
    A_REAL_MARKUP, SECOND_QUANTITY, WHAT_IT_WOULD_BILL,
    ATenantWithUnresolvedPostingsMixin, declares_a_markup)
from apps.metering.queries import RECEIPTS_ARE_AT
from apps.platform.customers.models import Customer
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY)
from core.vocabulary import PRICING_STATUS_UNKNOWN

#: The API root every path below is mounted under. Split out because the route
#: walker keys on the MOUNT path — the shape `test_role_floors` reads and the
#: shape `RECEIPTS_ARE_AT` is written in — while an HTTP client needs the root.
ROOT = "/api/v1"

QUEUE = "/metering/pricing/unresolved-queue"
PROJECTION = "/metering/pricing/projected-adjustment"
WAIVED = "/metering/pricing/waived-loss"
SURFACES = (QUEUE, PROJECTION, WAIVED)

#: The run these three project from, so that "no mutating route is added" can
#: be asserted against the surface that IS allowed to write.
RUNS = "/metering/pricing/resolution-runs"

PROJECTED = "projected_billed_cost_micros"


class _AReadableBacklogMixin(ATenantWithUnresolvedPostingsMixin):

    def setUp(self):
        super().setUp()
        self.http = Client()
        self.key, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def _as(self, role):
        TenantApiKey.objects.filter(pk=self.key.pk).update(role=role)
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def read(self, path, role=READ, **params):
        return self.http.get(f"{ROOT}{path}", data=params, **self._as(role))

    def body(self, path, **params):
        answered = self.read(path, **params)
        self.assertEqual(answered.status_code, 200, answered.content)
        return answered.json()


class ThreeReadsAndNoFourthVerbTest(_AReadableBacklogMixin, TestCase):
    """AC 3's structural half. A surface that cannot be written to cannot move
    money, and that is a property of what the API publishes rather than of what
    three handlers happen to do."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

    def test_none_of_the_three_publishes_a_mutating_verb(self):
        """⚠ ENUMERATED FROM THE LIVE API. A handler that only reads today
        proves nothing about a POST somebody adds to the same path tomorrow;
        what is asserted is the published method set."""
        published = _methods_by_path()

        for path in SURFACES:
            with self.subTest(path=path):
                self.assertEqual(published[path], {"GET"})

    def test_the_run_beside_them_is_the_one_that_writes(self):
        """The control that stops the case above being vacuous: the walker CAN
        see a mutating verb on this router, and does."""
        self.assertEqual(_methods_by_path()[RUNS], {"POST"})

    def test_every_one_of_them_floors_at_read(self):
        from api.v1.metering_endpoints import (
            get_projected_adjustment, get_unresolved_queue, get_waived_loss)

        for handler in (get_unresolved_queue, get_projected_adjustment,
                        get_waived_loss):
            with self.subTest(handler=handler.__name__):
                self.assertEqual(handler._role_floor, READ)

    def test_a_write_role_may_read_them_because_reading_decides_nothing(self):
        for path in SURFACES:
            with self.subTest(path=path):
                self.assertEqual(self.read(path, role=WRITE).status_code, 200)

    def test_a_metering_only_tenant_may_read_all_three(self):
        """⚠ THE GATE IS METERING'S, FOR #363'S REASON. Half of what these
        report is a supplier cost UBB never learned, which is owed to a tenant
        who charges nobody through UBB; the billing gate would lock exactly
        that tenant out of the queue built for them."""
        tenant = Tenant.objects.create(name="Meters", products=["metering"])
        _, raw = TenantApiKey.create_key(tenant, label="k")

        for path in SURFACES:
            with self.subTest(path=path):
                answered = self.http.get(
                    f"{ROOT}{path}",
                    **{"HTTP_AUTHORIZATION": f"Bearer {raw}"})
                self.assertEqual(answered.status_code, 200)

    def test_a_customer_this_tenant_does_not_have_is_a_404(self):
        """An empty answer would read as *there is nothing to recover for
        them*, which is a different and much worse statement."""
        theirs = Customer.objects.create(
            tenant=Tenant.objects.create(name="Other"), external_id="theirs")

        for path in SURFACES:
            with self.subTest(path=path):
                self.assertEqual(
                    self.read(path, selected_customer_id=str(theirs.id))
                    .status_code, 404)

    def test_a_stated_window_past_a_year_is_refused_on_all_three(self):
        """`docs/conventions/api-contract.md`: a computed report is
        cursor-exempt but PARAMETER-BOUNDED, and an explicit date window past
        366 days is a `validation_error`. It bites hardest on the waived
        report, whose figure is a whole-history GROUP BY with no row cap of its
        own — and it is what keeps an expensive read safe at the Read floor."""
        for path in SURFACES:
            with self.subTest(path=path):
                answered = self.read(
                    path, selected_from="2024-01-01T00:00:00Z",
                    selected_to="2026-01-02T00:00:00Z")

                self.assertEqual(answered.status_code, 422)
                self.assertEqual(
                    answered.json()["type"].rsplit("/", 1)[-1],
                    "validation_error")

    def test_a_window_inside_a_year_is_answered(self):
        """The control: the refusal is about the SPAN, not about stating a
        window at all. Without this, a surface that refused every date range
        would pass the case above."""
        for path in SURFACES:
            with self.subTest(path=path):
                self.assertEqual(
                    self.read(path, selected_from="2026-01-01T00:00:00Z",
                              selected_to="2026-06-01T00:00:00Z").status_code,
                    200)


class TheDeclaredRowsNameTheirCountsTest(_AReadableBacklogMixin, TestCase):
    """AC 7. ⚠ A `Schema` THAT DOES NOT NAME A KEY DROPS IT.

    A completeness count attached in the read contract survives on an untyped
    rollup and vanishes from the one declared row — so the only surface a drift
    gate can see is the only one that loses the field (#327, spec §24). Both
    halves are asserted: the schema DECLARES the key, and the wire body CARRIES
    it, because a declaration nothing exercises would not catch a serializer
    that stopped supplying the value.
    """

    #: Each declared schema and the completeness count it owes. The projection
    #: owes two, and they are on different nodes because they answer about
    #: different populations: how many EXAMINED postings could not be valued is
    #: per customer, and how many the bound never examined cannot be attributed
    #: to a customer at all.
    DECLARED = (
        (schemas.UnresolvedQueueTotals, UNRESOLVED_EVENT_COUNT_KEY),
        (schemas.ProjectedAdjustmentRow, UNPRICED_EVENT_COUNT_KEY),
        (schemas.ProjectedAdjustmentOut, "postings_not_examined"),
        (schemas.WaivedLossRow, UNRESOLVED_EVENT_COUNT_KEY),
    )

    def setUp(self):
        super().setUp()
        self.a_rate_priced_against_a_typo()
        self.unpriced = self.a_posting("unpriced")
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)
        # A waived charge, so the waived surface has a row to carry a count on.
        self.waived = self.a_posting("waived", measures=SECOND_QUANTITY)

    def test_each_declared_row_names_its_completeness_count(self):
        for row, count_key in self.DECLARED:
            with self.subTest(row=row.__name__):
                self.assertIn(count_key, row.model_fields)

    def test_and_the_wire_body_carries_it(self):
        for body, key, count_key in (
                (self.body(QUEUE)["totals"], "totals",
                 UNRESOLVED_EVENT_COUNT_KEY),
                (self.body(PROJECTION)["rows"], "rows",
                 UNPRICED_EVENT_COUNT_KEY),
                (self.body(WAIVED)["rows"], "rows",
                 UNRESOLVED_EVENT_COUNT_KEY)):
            with self.subTest(surface=key):
                self.assertTrue(body, "no row to carry a count")
                for row in body:
                    self.assertIn(count_key, row)

    def test_the_waived_figure_reaches_the_wire_with_its_basis(self):
        """AC 5, over the surface. The sentence travels with the number."""
        answered = self.body(WAIVED)

        self.assertIn("supplier", answered["basis"].lower())
        self.assertEqual(answered["rows"][0]["waived_event_count"], 1)
        self.assertEqual(answered["rows"][0][UNRESOLVED_EVENT_COUNT_KEY], 1)
        self.assertEqual(answered["rows"][0]["provider_cost_micros"], 0)

    def test_every_surface_carries_its_own_basis(self):
        for path in SURFACES:
            with self.subTest(path=path):
                self.assertTrue(self.body(path)["basis"].strip())


class TheQueueIsPagedLikeEveryOtherListTest(_AReadableBacklogMixin, TestCase):
    """A working list a tenant can get to the end of.

    ⚠ **THE ENVELOPE IS EXERCISED RATHER THAN INHERITED.** `page` is covered by
    `test_pagination.py` for its own shape, but what this route hands it —
    `time_field="effective_at"` and the queue's own serializer — is this
    route's, and a wrong time field would page correctly against a stale
    ordering and silently repeat or skip rows. That is invisible on one page.
    """

    def setUp(self):
        super().setUp()
        self.postings = [self.a_posting(f"k{index}") for index in range(3)]

    def test_a_cursor_reaches_the_rest_and_no_row_is_seen_twice(self):
        first = self.body(QUEUE, limit=2)

        self.assertTrue(first["has_more"])
        self.assertIsNotNone(first["next_cursor"])

        second = self.body(QUEUE, limit=2, cursor=first["next_cursor"])

        self.assertFalse(second["has_more"])
        seen = [row["usage_event_id"] for row in first["data"] + second["data"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen),
                         {str(posting.id) for posting in self.postings})

    def test_the_totals_are_over_the_whole_filter_and_not_the_page(self):
        """The page is two rows; the total is about three. A totals block that
        moved with the page would make a tenant's backlog look smaller every
        time they paged into it."""
        first = self.body(QUEUE, limit=2)

        self.assertEqual(len(first["data"]), 2)
        self.assertEqual(first["totals"][0]["queued_event_count"], 3)


class NoAmountUBBDoesNotHaveCrossesAsANumberTest(
        _AReadableBacklogMixin, TestCase):
    """AC 8, over the whole body of all three surfaces."""

    def setUp(self):
        super().setUp()
        self.unpriced = self.a_posting("unpriced")

    def test_the_status_is_a_status_and_never_a_money_field(self):
        row = self.body(QUEUE)["data"][0]

        self.assertEqual(row["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertIsNone(row["billed_cost_micros"])

    def test_no_money_field_anywhere_holds_a_word(self):
        """⚠ WALKED RATHER THAN LISTED. A field added to one of these rows
        later is covered by this the day it is added, which a named list of two
        would not be."""
        for path in SURFACES:
            for key, value in _money_fields(self.body(path)):
                with self.subTest(path=path, key=key):
                    self.assertIsInstance(value, (int, type(None)))
                    self.assertNotEqual(value, PRICING_STATUS_UNKNOWN)


class TheReceiptsBehindTheFigureAreReachableTest(
        _AReadableBacklogMixin, TestCase):
    """AC 2's second half. A figure with unreachable receipts is a number a
    tenant cannot take to their customer."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

    def test_the_path_the_projection_publishes_is_a_route_that_exists(self):
        """⚠ NOTHING TYPE-CHECKS A PATH QUOTED IN PROSE, and this one is
        exported verbatim into the contract and the generated SDK — a reader
        following a route that had moved would be sent nowhere."""
        self.assertIn(RECEIPTS_ARE_AT, _methods_by_path())
        self.assertIn(RECEIPTS_ARE_AT, self.body(PROJECTION)["basis"])

    def test_every_published_mention_of_a_receipt_path_names_that_one(self):
        """⚠ THE CONSTANT ALONE CANNOT MAKE THE COPIES AGREE. A docstring
        cannot interpolate one, so the route hand-types the path while the
        response's `basis` is built from it — two spellings, both exported
        into `openapi/v1.json` and the generated SDK, one of them free to
        drift. This is what stops them: anything published here that mentions a
        usage-event receipt path must mention exactly the one the constant
        names, so a route that moves turns this red rather than sending a
        reader nowhere.

        Only DOCSTRINGS and response values are published — a `#:` field
        comment reaches neither pydantic nor the exporter — so the route's
        docstring and the `basis` are the whole published set.
        """
        from api.v1.metering_endpoints import get_projected_adjustment

        published = {
            "the route docstring": get_projected_adjustment.__doc__,
            "the schema docstring": schemas.ProjectedAdjustmentRow.__doc__ or "",
            "the response basis": self.body(PROJECTION)["basis"],
        }
        named_one = {where: text for where, text in published.items()
                     if "/metering/usage/" in text}

        self.assertTrue(named_one, "no published prose names a receipt path — "
                                   "this control has stopped controlling")
        for where, text in named_one.items():
            with self.subTest(where=where):
                self.assertIn(RECEIPTS_ARE_AT, text)

    def test_each_named_posting_answers_with_the_record_explaining_it(self):
        row = self.body(PROJECTION)["rows"][0]

        self.assertEqual(row[PROJECTED], WHAT_IT_WOULD_BILL)
        for event_id in row["usage_event_ids"]:
            with self.subTest(event_id=event_id):
                detail = self.body(
                    RECEIPTS_ARE_AT.replace("{event_id}", event_id))
                self.assertEqual(detail["id"], event_id)

    def test_reading_the_projection_bills_nobody(self):
        """AC 3 at the surface: the figure exists, and nothing follows from
        reading it."""
        from apps.billing.invoicing.models import Invoice
        from apps.billing.wallets.models import WalletTransaction

        self.assertEqual(self.body(PROJECTION)["rows"][0][PROJECTED],
                         WHAT_IT_WOULD_BILL)

        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(WalletTransaction.objects.count(), 0)
        self.posting.refresh_from_db()
        self.assertEqual(self.posting.pricing_status, PRICING_STATUS_UNKNOWN)
        self.assertIsNone(self.posting.billed_cost_micros)

    def test_the_run_beside_it_is_how_the_figure_becomes_real(self):
        """The control: the projection declined to write what a run then
        writes, so the case above is about a refusal rather than about an
        unreachable state."""
        self.http.post(f"{ROOT}{RUNS}", data=json.dumps({}),
                       content_type="application/json", **self._as(ADMIN))

        self.posting.refresh_from_db()
        self.assertEqual(self.posting.billed_cost_micros, WHAT_IT_WOULD_BILL)


def _methods_by_path():
    """Every published mount path on the one API, and the verbs it answers.

    The path shape is `test_role_floors._iter_ops`'s — mount-prefixed, without
    the `/api/v1` root — so that a path named in prose can be compared against
    the live API without either side spelling the root.
    """
    published = {}
    for prefix, router in api._routers:
        for path, view in router.path_operations.items():
            segments = [s for s in (prefix.strip("/"), path.strip("/")) if s]
            full = "/" + "/".join(segments)
            for operation in view.operations:
                published.setdefault(full, set()).update(operation.methods)
    return published


def _money_fields(body, prefix=""):
    """Every `*_micros` leaf in a response body, with its path."""
    if isinstance(body, dict):
        for key, value in body.items():
            if key.endswith("_micros"):
                yield f"{prefix}{key}", value
            else:
                yield from _money_fields(value, prefix=f"{prefix}{key}.")
    elif isinstance(body, list):
        for index, item in enumerate(body):
            yield from _money_fields(item, prefix=f"{prefix}{index}.")
