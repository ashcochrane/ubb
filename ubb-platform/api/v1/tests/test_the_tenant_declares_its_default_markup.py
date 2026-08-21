"""Declaring the tenant's default markup rung, and withdrawing it (#357).

**THE RUNG THAT PRICES MOST EVENTS, MADE DECLARABLE.** Where the books in play
hold no rule for a quantity, the customer's price is a percentage over what UBB
knows the call cost. A tenant has to be able to say what that percentage is,
read it back, and take it away — through routes that exist.

**⚠ AN ABSENT DECLARATION IS NOT A ZERO, AND THIS MODULE IS WHERE THAT IS
ASSERTED ON THE WIRE.** UBB ships no catalogue: no seeded markup, no default
percentage, no starter value. A tenant that has declared nothing has no rung and
their unruled events price to `unknown`. A tenant who declares zero has decided
to charge exactly what their calls cost, and that settles. The two are different
facts and the response tells them apart — null against `0` — because the whole
defect this slice deletes is a number standing in for a decision nobody made.

**TWO ACTS, TWO AUDIT ACTIONS, AND THE RECORDING FUNCTION REFUSES AN
UNREGISTERED NAME.** That refusal is what forces a route and its action into one
commit, so there is no window in which a route writes a name the registry does
not know. Declaring and withdrawing are split under the registry's own rule —
one action per record per kind of act, *"split now, when it is free"* — because
a correction to a declared percentage is still a declaration, while a withdrawal
leaves the tenant with no rung at all and a governance reader must not have to
read metadata to see which happened.

**GOVERNANCE, NOT TELEMETRY.** Both writes decide what a customer is charged, so
neither takes the audit sweep's exemption list — the carve there is for usage
ingestion and the start-gate call, and this is neither.
"""
import json

from django.test import Client, TestCase

from apps.metering.pricing.models import TenantDefaultMarkup
from apps.metering.pricing.services.markup_service import MarkupService
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey

DECLARED = "tenant_default_markup.declared"
WITHDRAWN = "tenant_default_markup.withdrawn"

ROUTE = "/api/v1/metering/pricing/default-markup"


class _TheRungsRoutesMixin:
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Rung", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _declare(self, micro_percent):
        return self.http.put(
            ROUTE, data=json.dumps({"markup_micro_percent": micro_percent}),
            content_type="application/json", **self._auth())

    def _withdraw(self):
        return self.http.delete(ROUTE, **self._auth())

    def _read(self):
        return self.http.get(ROUTE, **self._auth())


class ATenantDeclaresAndWithdrawsItsRungTest(_TheRungsRoutesMixin, TestCase):
    """The two acts, and the read that makes them usable."""

    def test_a_declared_rung_is_stored_read_back_and_resolves(self):
        declared = self._declare(20_000_000)

        self.assertEqual(declared.status_code, 200)
        self.assertEqual(declared.json()["markup_micro_percent"], 20_000_000)
        self.assertEqual(self._read().json()["markup_micro_percent"],
                         20_000_000)
        # And it is the rung resolution reads, not merely a stored row.
        self.assertEqual(
            MarkupService.resolve(self.tenant, self.customer).markup_micro_percent,
            20_000_000)

    def test_re_declaring_corrects_the_rung_rather_than_adding_one(self):
        """A correction to a declared percentage is still a declaration, which
        is why one action covers both and why exactly one row survives."""
        self._declare(20_000_000)
        again = self._declare(35_000_000)

        self.assertEqual(again.json()["markup_micro_percent"], 35_000_000)
        self.assertEqual(
            TenantDefaultMarkup.objects.filter(tenant=self.tenant).count(), 1)

    def test_withdrawing_leaves_the_tenant_with_no_rung_at_all(self):
        self._declare(20_000_000)

        withdrawn = self._withdraw()

        self.assertEqual(withdrawn.status_code, 200)
        self.assertEqual(withdrawn.json()["status"], "withdrawn")
        self.assertIsNone(self._read().json()["markup_micro_percent"])
        self.assertIsNone(MarkupService.resolve(self.tenant, self.customer))

    def test_withdrawing_nothing_is_idempotent_and_records_no_act(self):
        """There was no act, so there is no entry. An audit ledger that logged
        a withdrawal nobody performed would answer "when did this tenant stop
        having a markup" with a date on which nothing happened."""
        response = self._withdraw()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "no_declaration")
        self.assertFalse(AuditRecord.objects.filter(
            tenant_id=self.tenant.id).exists())


class NoRungIsSeededAndAnAbsentOneIsNotAZeroTest(_TheRungsRoutesMixin,
                                                 TestCase):
    """UBB ships no catalogue, asserted where a helpful default would land.

    The constraint most likely to be violated by a convenience: a response that
    answered `0` for a tenant who has declared nothing would say they had
    decided to charge exactly what their calls cost.
    """

    def test_a_tenant_that_has_declared_nothing_reads_back_null(self):
        response = self._read()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["markup_micro_percent"])
        self.assertFalse(TenantDefaultMarkup.objects.exists())

    def test_a_declared_zero_is_a_decision_and_reads_back_as_one(self):
        self._declare(0)

        self.assertEqual(self._read().json()["markup_micro_percent"], 0)
        self.assertEqual(
            MarkupService.resolve(self.tenant, self.customer).markup_micro_percent,
            0)

    def test_declaring_requires_the_percentage_to_be_stated(self):
        """No default on the request field either: a rung is declared on
        purpose, and a body that omitted it would declare zero by accident."""
        response = self.http.put(
            ROUTE, data=json.dumps({}), content_type="application/json",
            **self._auth())

        self.assertEqual(response.status_code, 422)
        self.assertFalse(TenantDefaultMarkup.objects.exists())

    def test_a_negative_percentage_is_refused(self):
        response = self._declare(-1)

        self.assertEqual(response.status_code, 422)
        self.assertFalse(TenantDefaultMarkup.objects.exists())


class BothActsAreRecordedUnderTheirOwnNameTest(_TheRungsRoutesMixin, TestCase):
    """The ledger says which act happened, not merely that something did."""

    def test_declaring_records_the_declaration_with_the_percentage(self):
        self._declare(20_000_000)

        entry = AuditRecord.objects.get(tenant_id=self.tenant.id)
        self.assertEqual(entry.action, DECLARED)
        self.assertEqual(entry.resource_type, "tenant_default_markup")
        self.assertEqual(entry.metadata["markup_micro_percent"], 20_000_000)

    def test_withdrawing_records_the_other_name(self):
        self._declare(20_000_000)
        self._withdraw()

        self.assertEqual(
            [entry.action for entry in
             AuditRecord.objects.filter(tenant_id=self.tenant.id).order_by(
                 "created_at")],
            [DECLARED, WITHDRAWN])

    def test_the_two_names_are_registered_and_distinct(self):
        self.assertTrue(is_registered_action(DECLARED))
        self.assertTrue(is_registered_action(WITHDRAWN))
        self.assertNotEqual(DECLARED, WITHDRAWN)

    def test_the_recording_function_refuses_a_name_nobody_registered(self):
        """The mechanism that forces a route and its action into one commit.

        Driven over a near-miss of each real name rather than over an obvious
        nonsense string, because what this has to catch is a typo or a name
        somebody meant to add and did not.
        """
        for unregistered in (f"{DECLARED}_", "tenant_default_markup.set",
                             "tenant_default_markup.deleted"):
            with self.subTest(unregistered):
                self.assertFalse(is_registered_action(unregistered))
                with self.assertRaisesRegex(ValueError, "unregistered audit"):
                    audit_record(action=unregistered,
                                 tenant_id=self.tenant.id,
                                 resource_type="tenant_default_markup")

    def test_neither_route_takes_the_audit_sweeps_exemption(self):
        """Both writes decide what a customer is charged, so both are
        governance. The exemption list is for usage ingestion and the start-gate
        call — read it here rather than trusting the sweep's own count, which
        would stay green if a route joined the carve."""
        from api.v1.tests.test_audit_sweep import _EXEMPT

        self.assertNotIn(("PUT", "/metering/pricing/default-markup"), _EXEMPT)
        self.assertNotIn(("DELETE", "/metering/pricing/default-markup"),
                         _EXEMPT)

    def test_both_routes_carry_the_marker_the_mutating_pin_reads(self):
        """The #82 pin walks the live API for exactly this attribute, and a
        route carrying neither it nor an exemption turns it red."""
        from api.v1.tests.test_audit_sweep import mutating_operations

        marked = {(method, path): getattr(view, "_audit_actions", ())
                  for method, path, view in mutating_operations()
                  if path == "/metering/pricing/default-markup"}

        self.assertEqual(marked, {("PUT", "/metering/pricing/default-markup"):
                                  (DECLARED,),
                                  ("DELETE", "/metering/pricing/default-markup"):
                                  (WITHDRAWN,)})
