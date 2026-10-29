"""A tenant that meters and bills elsewhere is `external`, and its posture derives (slice 8).

The registry's `customer_billing_mode` named this value `external` from the
start (`domain-vocabulary/concepts/economics.yaml`); slice 8 brings the tenant
row, its config read and write, the console and the SDK to the word, and pays
the thirteen migration-ledger entries that recorded the debt. The posture the
registry derives from it — `tenant_posture`, never stored (ADR-0006 §4) — is
served read-only beside it so a caller need not reconstruct the mapping.

Before the cutover (#190) this module also ran `tenants/0029` through the
executor and back, moving every stored row from the retired spelling to
`external`; that data step left with the squashed chain. The closed set it
left the table holding — `ck_tenant_billing_mode_known` — is pinned below.
"""
import json

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase

from api.v1.tests._helpers import retired_aliases
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_EXTERNAL,
    CUSTOMER_BILLING_MODE_VALUES,
    TENANT_POSTURE_FULL_BILLING,
    TENANT_POSTURE_METERING_ONLY,
)

#: The spelling slice 8 retires, as a request might still send it — read off
#: the registry that retired it, because a living file may not spell it.
(RETIRED,) = retired_aliases("economics", "customer_billing_mode")


class TheConfigServesTheModeAndItsPostureTest(TestCase):

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Elsewhere", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def _config(self):
        answered = self.http_client.get(
            "/api/v1/tenant/config", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(answered.status_code, 200, answered.content)
        return answered.json()

    def _patch(self, body):
        return self.http_client.patch(
            "/api/v1/tenant/config", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_a_new_tenant_bills_externally_and_its_posture_is_metering_only(self):
        body = self._config()

        self.assertEqual((body["billing_mode"], body["tenant_posture"]),
                         (CUSTOMER_BILLING_MODE_EXTERNAL, TENANT_POSTURE_METERING_ONLY))

    def test_the_posture_follows_the_mode_and_is_never_stored(self):
        self.assertEqual(
            {mode: Tenant(billing_mode=mode).tenant_posture
             for mode in CUSTOMER_BILLING_MODE_VALUES},
            {"external": TENANT_POSTURE_METERING_ONLY,
             "prepaid": TENANT_POSTURE_FULL_BILLING,
             "postpaid": TENANT_POSTURE_FULL_BILLING})
        self.assertNotIn("tenant_posture",
                         {field.name for field in Tenant._meta.get_fields()})

    def test_the_retired_spelling_is_refused_by_name_and_writes_nothing(self):
        self.tenant.enforcement_mode = "off"
        self.tenant.save(update_fields=["enforcement_mode"])

        answered = self._patch({"billing_mode": RETIRED,
                                "enforcement_mode": "enforcing"})

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertEqual(answered.json()["code"], "invalid_config")
        self.tenant.refresh_from_db()
        self.assertEqual((self.tenant.billing_mode, self.tenant.enforcement_mode),
                         (CUSTOMER_BILLING_MODE_EXTERNAL, "off"))

    def test_external_is_admitted_by_its_final_name(self):
        answered = self._patch({"billing_mode": CUSTOMER_BILLING_MODE_EXTERNAL})

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(answered.json()["tenant_posture"], TENANT_POSTURE_METERING_ONLY)


class TheDatabaseHoldsTheClosedSetTest(TestCase):
    """`choices=` is a form courtesy; the CHECK is what the doors that skip the
    route meet."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Elsewhere", products=["metering"])

    def test_the_retired_spelling_is_refused_through_every_door_that_skips_save(self):
        doors = {
            "QuerySet.update()": lambda: Tenant.objects.filter(
                pk=self.tenant.pk).update(billing_mode=RETIRED),
            "raw SQL": lambda: connection.cursor().execute(
                "UPDATE ubb_tenant SET billing_mode = %s WHERE id = %s",
                [RETIRED, str(self.tenant.pk)]),
        }
        for name, door in doors.items():
            with self.subTest(door=name):
                with self.assertRaisesRegex(IntegrityError,
                                            "ck_tenant_billing_mode_known"):
                    with transaction.atomic():
                        door()
                self.tenant.refresh_from_db()
                self.assertEqual(self.tenant.billing_mode,
                                 CUSTOMER_BILLING_MODE_EXTERNAL)
