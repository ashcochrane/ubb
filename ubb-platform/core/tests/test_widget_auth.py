import uuid
import jwt
import time
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from core.widget_auth import create_widget_token, verify_widget_token


class WidgetTokenTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    def test_create_and_verify_token(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )
        payload = verify_widget_token(token)
        self.assertEqual(payload["sub"], str(self.customer.id))
        self.assertEqual(payload["tid"], str(self.tenant.id))

    def test_expired_token_rejected(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id),
            expires_in=-1,
        )
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_wrong_secret_rejected_via_two_step(self):
        """Token signed with wrong secret fails two-step verification."""
        token = create_widget_token(
            "wrong_secret_that_doesnt_match", str(self.customer.id), str(self.tenant.id)
        )
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_invalid_tid_uuid_rejected_without_db_query(self):
        """Non-UUID tid is rejected before any DB lookup."""
        payload = {
            "sub": str(self.customer.id),
            "tid": "not-a-uuid",
            "iss": "ubb",
            "exp": int(time.time()) + 900,
        }
        token = jwt.encode(payload, "any_secret", algorithm="HS256")
        result = verify_widget_token(token)
        self.assertIsNone(result)

    def test_tenant_auto_generates_widget_secret(self):
        self.assertTrue(len(self.tenant.widget_secret) > 0)

    def test_widget_secret_is_unique_per_tenant(self):
        tenant2 = Tenant.objects.create(name="Test2")
        self.assertNotEqual(self.tenant.widget_secret, tenant2.widget_secret)

    def test_rotate_widget_secret(self):
        old_secret = self.tenant.widget_secret
        self.tenant.rotate_widget_secret()
        self.assertNotEqual(self.tenant.widget_secret, old_secret)
        # Old token signed with old secret should fail
        token = create_widget_token(old_secret, str(self.customer.id), str(self.tenant.id))
        result = verify_widget_token(token)
        self.assertIsNone(result)
