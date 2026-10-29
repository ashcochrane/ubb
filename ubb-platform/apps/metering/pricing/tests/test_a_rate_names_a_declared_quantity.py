"""A rate names the declared quantity it prices, or it is refused (#326).

Slice 2 renamed the column and said, in the model, in the migration and in a
test module built to fail today, that slice 3 would replace the name with a
reference to the declared record the name is a name *of*. This module is where
that lands. Three separate claims live here and they fail for different reasons:

* **A rate references the declaration its name resolves to** — the tenant's
  own, and the earliest where several carry the name. Until the cutover (#190)
  this claim was also that the conversion (`pricing/0019`) carried its data,
  hand-ordered under ADR-0007 §1 with its reverse RUN here; the squash deleted
  that migration and every row in the pre-reference shape, so its operation
  list and its data function retired with it, and what the conversion chose is
  asserted of the lookup a rule written today goes through.
* **A rate naming a quantity nobody declared is refused**, at the route with a
  422 that spends nothing, and at the database for every other door
  (`trg_rate_names_a_declaration`, whose reverse is proven centrally in
  `apps/platform/tests/test_the_database_rules_are_carried.py`).
* **A rate that names no declaration is deactivated** — the shape the
  conversion left for a name it could not place: it keeps its row, it keeps
  its name, it stops resolving, and it is neither deleted nor pointed at
  somebody else's declaration.

**WHAT DID NOT CHANGE IS ASSERTED TOO, because it is the thing most likely to
have.** Resolution still matches on the NAME, so a rate that leaves the Event
Type unpinned still prices the quantity under every Event Type declaring it.
Matching by the reference's identity instead would have looked like a tidier
spelling of the same rule and been a different one.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The cost/price discriminator,
the book pointer and the shape-of-charge column are all names slice 4 owns, and
the ledger's counts are ceilings as much as floors — so rates are built through
`_helpers.cost_rate_in_default_book`, which carries the first for its callers,
and the other two are never passed at all because the model's defaults are
already what every case here wants.
"""

import json

from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_ADD, LINE_RATE, NAMES_ONE_QUANTITY_CHECK, PricingBookPublish,
    Rate)
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    cost_book, cost_rate_in_default_book)
from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.quantities import declaration_named
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

#: The rule the check could not state — who may be INSERTed (#326, review pass).
DECLARATION_TRIGGER = "trg_rate_names_a_declaration"

DECLARED_NAME = "input_tokens"
UNDECLARED_NAME = "typo_tokens"

#: The partial unique index the conversion rebuilt over the reference. Named
#: because every refusal here asserts WHICH mechanism refused: several on this
#: table answer `IntegrityError` and they hold entirely different things.
#: ⚠ ONE KEY BECAME TWO (#368), and this module's cases build COST rules —
#: a rule points at a Pricing Book or at a cost book, and a single key naming
#: both columns would carry a NULL on every row, which Postgres treats as
#: distinct. This is the half that guards the rules these cases write.
ACTIVE_ROW_UNIQUE = "uq_rate_active_in_cost_book"


def _tenant(name="T"):
    return Tenant.objects.create(name=name, default_currency="usd")


class ARateReferencesTheEarliestDeclarationOfItsNameTest(TestCase):
    """WHAT THE CONVERSION CHOSE, asked of the lookup a rule written today uses.

    Locality means one tenant can carry one name under two Event Types. Which
    one a rate references changes nothing it prices — the resolver matches on
    the name — but it must be one deterministic pick, or two rates written for
    one name in one book stop colliding and the unique constraint over the
    reference quietly stops refusing what it refuses
    (`TheRebuiltObjectsStillEnforceWhatTheyDidTest`). The pick is the earliest
    declaration (`quantities.declaration_named`).

    Until the cutover (#190) this was asserted of `pricing/0019`'s own data
    function, beside the claim that the live lookup agreed with it. The squash
    deleted the function; the live half is the one that outlives it, and it is
    driven here through the act that writes every rule now — a publish.
    """

    def test_a_rule_published_today_references_the_earliest_declaration(self):
        tenant = _tenant()
        first = declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        second = Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        book = cost_book(tenant, key="openai", provider="openai")

        BookService.publish_declared(BookService.declare(
            book, [{"line": LINE_RATE, "kind": CHANGE_ADD,
                    "measurement_key": DECLARED_NAME, "provider": "openai",
                    "rate_per_unit_micros": 5}]))

        rate = Rate.objects.get(cost_book=book)
        self.assertEqual(rate.measurement_id, first.id)
        self.assertNotEqual(rate.measurement_id, second.id)
        self.assertEqual(
            declaration_named(tenant=tenant, measurement_key=DECLARED_NAME).id,
            rate.measurement_id)


class ARateNamingAnUndeclaredQuantityIsRefusedTest(TestCase):
    """The point of the conversion, asked at both doors it has.

    A typo used to sit on a rate matching nothing, costing nothing and looking
    configured. The tenant-facing answer is a 422 naming the fix; the answer for
    every other door — a script, a shell, a later service — is the database's,
    because a model-level guard is not enforcement (ADR-0007 §2).
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Refusal", products=["metering"], default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="rates")
        self.http = Client()
        # Built through the helper rather than over the route: the book create
        # body names the cost/price discriminator, which is a retired word slice
        # 4 owns and whose ledger count is a ceiling as much as a floor.
        self.book = cost_book(self.tenant, key="openai", provider="openai").id

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _add_rate(self, measurement_key):
        """Adding a rule, through the only surface that still does it (#367).

        This was the immediate add-a-rule route until that route was deleted:
        every change to a book is a publish now, so a rule arrives as a declared
        change and the refusal it meets is the same one, raised while the tenant
        is still deciding rather than after a row was written. The route moved;
        the claim did not.
        """
        return self._post(
            f"/api/v1/metering/pricing/books/{self.book}/publishes",
            {"changes": [{"line": LINE_RATE, "kind": CHANGE_ADD,
                          "measurement_key": measurement_key,
                          "provider": "openai",
                          "rate_per_unit_micros": 5}]})

    def test_the_route_refuses_a_name_this_tenant_has_not_declared(self):
        self.assertFalse(
            Measurement.objects.filter(code=UNDECLARED_NAME).exists())

        response = self._add_rate(UNDECLARED_NAME)

        self.assertEqual(response.status_code, 422, response.content)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        # The name the tenant sent, and what to do about it. A refusal that
        # named neither would send them to read the source.
        self.assertIn(UNDECLARED_NAME, body["detail"])
        self.assertIn("declare", body["detail"])

    def test_the_same_name_is_accepted_once_it_is_declared(self):
        """The control. Without it the refusal above passes on a broken route."""
        declares_a_quantity(self.tenant, UNDECLARED_NAME)

        response = self._add_rate(UNDECLARED_NAME)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [change["measurement_key"] for change in response.json()["diff"]],
            [UNDECLARED_NAME])

    def test_a_name_only_another_tenant_declared_is_refused(self):
        """The one direction a reference must never point.

        Matching on the name alone would hand this tenant's rule the other
        tenant's declaration, and every later read would be a cross-tenant one;
        nothing about a name says who declared it. Until the cutover (#190) this
        was asserted of `pricing/0019`'s backfill, which left such a rate
        placeless; a rule written today meets the lookup instead, and the
        lookup is the tenant's own.
        """
        elsewhere = _tenant("elsewhere")
        declares_a_quantity(elsewhere, UNDECLARED_NAME)
        self.assertIsNone(declaration_named(tenant=self.tenant,
                                            measurement_key=UNDECLARED_NAME))

        response = self._add_rate(UNDECLARED_NAME)

        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn(UNDECLARED_NAME, response.json()["detail"])

    def test_the_refusal_spends_nothing(self):
        """A refusal placed under a write spends what it refuses (#324).

        The surface that adds a rule writes twice — the draft record, and the
        audit entry beside it — and the lookup that refuses is a pure read
        inside the planner, which runs before either. **That ordering is
        structural rather than chosen**: a change cannot be planned without the
        declaration the lookup returns, so this test cannot be made red by
        moving the lookup.

        It is here for what a diff will not show later. A refused request is
        expected to leave the tenant's account exactly as it was, and the way
        that stops being true is a NEW write appearing above the refusal — the
        shape #324 shipped and had to unpick, where an admission-time write
        recorded against a request that recorded nothing. A statement of the
        property, not a mutation of it.

        ⚠ It is about THIS refusal, not about the route in general: the
        instant-refusal twin lives in `test_a_book_changes_by_publishing.py`,
        which pins the order of the checks that hoist above the atomic block.
        Two different refusals, one property each.
        """
        drafts = PricingBookPublish.objects.count()
        rules = Rate.objects.count()
        # Every audit entry this tenant has, not the one this route writes: the
        # claim is that the refusal recorded NOTHING, and a per-action check
        # would pass while some other entry rode along beside it.
        recorded = AuditRecord.objects.filter(tenant_id=self.tenant.id).count()

        self.assertEqual(self._add_rate(UNDECLARED_NAME).status_code, 422)

        self.assertEqual(PricingBookPublish.objects.count(), drafts)
        self.assertEqual(Rate.objects.count(), rules)
        self.assertEqual(
            AuditRecord.objects.filter(tenant_id=self.tenant.id).count(),
            recorded)

    def test_the_database_refuses_a_new_rate_naming_an_undeclared_quantity(self):
        """THE DOOR THE ROUTE IS NOT STANDING AT, and the check does not close it.

        `ck_rate_names_one_quantity` was written to. It cannot: a check is
        evaluated against one row and is satisfied by a rate INSERTED with no
        reference and a loose name — which is exactly the defect this slice
        deletes, one `Rate.objects.create` away from the route that refuses it.
        Review found that; `trg_rate_names_a_declaration`, a `BEFORE INSERT`
        trigger (`pricing/0020`'s rule, carried into the pricing rules
        migration at the cutover, #190), is what actually closes it, and the
        message it raises carries the name that was refused.
        """
        self.assertFalse(
            Measurement.objects.filter(code=UNDECLARED_NAME).exists())
        with self.assertRaisesRegex(IntegrityError, UNDECLARED_NAME):
            Rate.objects.create(tenant=self.tenant,
                                undeclared_measurement_key=UNDECLARED_NAME)

    def test_a_row_may_not_claim_both_a_declaration_and_a_loose_name(self):
        """The check, on the write where it IS the mechanism.

        Exactly one of the two columns says which quantity a rate prices. A row
        carrying both would make `measurement_key` a question with two answers,
        which is the shape ADR-0006 §4 refuses everywhere else.

        The trigger does not fire here — its `WHEN` clause asks whether the
        reference is null and this row has one — so the refusal is the check's,
        and the assertion says which. Insert order matters on this table now: a
        `BEFORE` trigger runs ahead of the table's checks, so a test that drove
        this shape with a null reference would be asserting the other rule while
        reading as though it asserted this one.
        """
        declaration = declares_a_quantity(self.tenant, DECLARED_NAME)
        with self.assertRaisesRegex(IntegrityError, NAMES_ONE_QUANTITY_CHECK):
            Rate.objects.create(tenant=self.tenant, measurement=declaration,
                                undeclared_measurement_key=UNDECLARED_NAME)

    def test_a_deactivated_rate_may_not_be_stripped_of_its_name(self):
        """The check's other case, which only an UPDATE can reach.

        A placeless rate that lost its name would price nothing and say nothing
        — unreadable, unfixable, and indistinguishable from a row somebody meant
        to leave empty. The trigger cannot hold this: it fires on INSERT, and
        this row was not inserted placeless — it was made so by an UPDATE, the
        shape the conversion once left behind (`pricing/0019`, before the
        cutover, #190).
        """
        rate = cost_rate_in_default_book(self.tenant,
                                         measurement_key=DECLARED_NAME)
        Rate.objects.filter(pk=rate.pk).update(
            measurement=None, undeclared_measurement_key=UNDECLARED_NAME)

        with self.assertRaisesRegex(IntegrityError, NAMES_ONE_QUANTITY_CHECK):
            Rate.objects.filter(pk=rate.pk).update(
                undeclared_measurement_key="")


class ADeactivatedRateKeepsItsNameAndPricesNothingTest(TestCase):
    """What a tenant sees afterwards, which is the reason for the rule.

    Deleting the row would have destroyed the evidence they need to fix it;
    repointing it would have invented a declaration they never made. So it stays,
    it still says what it was written to price, and it prices nothing.
    """

    def setUp(self):
        self.tenant = _tenant()
        self.rate = cost_rate_in_default_book(
            self.tenant, provider="openai", measurement_key=DECLARED_NAME,
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        # The shape the conversion left behind for a name it could not place
        # (`pricing/0019`, before the cutover, #190), written directly because
        # the route cannot produce it — which is the point of the refusal above.
        Rate.objects.filter(pk=self.rate.pk).update(
            measurement=None, undeclared_measurement_key=UNDECLARED_NAME)
        self.rate.refresh_from_db()

    def test_it_still_answers_with_the_name_it_was_written_with(self):
        self.assertEqual(self.rate.measurement_key, UNDECLARED_NAME)

    def test_it_resolves_against_nothing_including_its_own_name(self):
        for name in (UNDECLARED_NAME, DECLARED_NAME):
            with self.subTest(quantity=name):
                self.assertIsNone(PricingService.resolve_the_cost_rule(
                    self.tenant, {"provider": "openai"}, name,
                    "usd", timezone.now()))

    def test_it_is_still_there(self):
        self.assertTrue(Rate.objects.filter(pk=self.rate.pk).exists())


class TheRebuiltObjectsStillEnforceWhatTheyDidTest(TestCase):
    """The unique constraint, driven rather than read.

    `test_the_rates_quantity_name_takes_the_canonical_name.py` asserts that both
    objects now name the reference; this asserts the one that has behaviour
    still HAS it. The two are different claims and the gap between them is where
    a rewritten constraint quietly stops refusing.
    """

    def test_two_active_rates_for_one_quantity_in_one_book_still_collide(self):
        tenant = _tenant()
        cost_rate_in_default_book(tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)
        # The constraint by name, not "something refused this": this index, the
        # check, the reference's foreign key and two triggers all answer
        # `IntegrityError` on this table, and the rule the models file states
        # for its own check applies here first.
        with self.assertRaisesRegex(IntegrityError, ACTIVE_ROW_UNIQUE):
            cost_rate_in_default_book(tenant, provider="openai",
                                      measurement_key=DECLARED_NAME)

    def test_the_pair_still_collides_when_the_name_is_declared_twice(self):
        """The case the conversion could have lost, and the reason for the pick.

        Two Event Types may each declare `input_tokens`; they are two records
        that happen to share a spelling. Resolution matches on the spelling, so
        two rates naming it in one book are still two rates that both match one
        event — and if the write had resolved the name to whichever declaration
        it liked, they would reference different rows and the constraint would
        let both stand. The lookup being deterministic is what keeps this red.
        """
        tenant = _tenant()
        declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)

        cost_rate_in_default_book(tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)
        with self.assertRaisesRegex(IntegrityError, ACTIVE_ROW_UNIQUE):
            cost_rate_in_default_book(tenant, provider="openai",
                                      measurement_key=DECLARED_NAME)


class ResolutionStillMatchesOnTheNameTest(TestCase):
    """WHAT THIS COMMIT DELIBERATELY DID NOT CHANGE.

    A rate holds the declared record now, and the tempting next step — match on
    that record instead of on its name — is a different rule wearing the same
    words. Declarations are Event-Type-local, so a rate with the Event Type
    unpinned prices the quantity under every Event Type that declares it, and
    identity matching would narrow that to one of them with nothing announcing
    the change. `Measurement`'s own docstring called this before the reference
    existed: *a Cost Rate still matches on `measurement_key`*.
    """

    def test_a_rate_prices_the_name_under_an_event_type_it_does_not_reference(self):
        tenant = _tenant()
        # Declared under one Event Type...
        declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        # ...and independently under another, which is a different record that
        # happens to share a spelling.
        Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        rate = cost_rate_in_default_book(
            tenant, provider="openai", measurement_key=DECLARED_NAME,
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)

        resolved = PricingService.resolve_the_cost_rule(
            tenant, {"provider": "openai", "event_type": "second.call"},
            DECLARED_NAME, "usd", timezone.now())

        self.assertEqual(resolved.id, rate.id)
        self.assertNotEqual(rate.measurement.event_type.key, "second.call")


class AQuantityARatePricesCannotBeWithdrawnTest(TestCase):
    """`PROTECT`, rendered as a 409 rather than as a 500.

    The refusal is the one `withdraw_event_category` already makes for the same
    shape. The alternative was to withdraw the declaration and deactivate the
    rates behind it, which would rewrite a tenant's pricing on their behalf.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Withdraw", products=["metering"], default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="withdraw")
        self.http = Client()
        self.declaration = declares_a_quantity(self.tenant, DECLARED_NAME)
        self.path = (f"/api/v1/event-types/"
                     f"{self.declaration.event_type.key}/measurements/"
                     f"{DECLARED_NAME}")

    def _withdraw(self):
        return self.http.delete(
            self.path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_it_is_refused_while_a_rate_prices_it(self):
        cost_rate_in_default_book(self.tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)

        response = self._withdraw()

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "conflict")
        self.assertIn(DECLARED_NAME, response.json()["detail"])
        self.assertTrue(
            Measurement.objects.filter(pk=self.declaration.pk).exists())

    def test_it_is_withdrawn_when_nothing_prices_it(self):
        """The control: the refusal above is about the rate, not about the route."""
        self.assertEqual(self._withdraw().status_code, 204)
        self.assertFalse(
            Measurement.objects.filter(pk=self.declaration.pk).exists())
