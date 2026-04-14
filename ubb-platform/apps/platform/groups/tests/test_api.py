import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.groups.models import Group


class GroupEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_create_group(self):
        response = self.client.post(
            "/api/v1/platform/groups",
            data=json.dumps({
                "name": "Property Search",
                "slug": "property_search",
                "margin_pct": 65.0,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "Property Search")
        self.assertEqual(body["slug"], "property_search")
        self.assertEqual(body["margin_pct"], 65.0)

    def test_create_group_duplicate_slug_returns_409(self):
        Group.objects.create(tenant=self.tenant, name="G1", slug="dup_slug")
        response = self.client.post(
            "/api/v1/platform/groups",
            data=json.dumps({
                "name": "G2",
                "slug": "dup_slug",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 409)

    def test_create_group_with_parent(self):
        parent = Group.objects.create(tenant=self.tenant, name="Parent", slug="parent")
        response = self.client.post(
            "/api/v1/platform/groups",
            data=json.dumps({
                "name": "Child",
                "slug": "child",
                "parent_id": str(parent.id),
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_id"], str(parent.id))

    def test_list_groups(self):
        Group.objects.create(tenant=self.tenant, name="G1", slug="g1")
        Group.objects.create(tenant=self.tenant, name="G2", slug="g2")
        response = self.client.get(
            "/api/v1/platform/groups",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]), 2)

    def test_list_groups_status_filter(self):
        Group.objects.create(tenant=self.tenant, name="G1", slug="g1")
        Group.objects.create(tenant=self.tenant, name="G2", slug="g2", status="archived")
        response = self.client.get(
            "/api/v1/platform/groups?status=active",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]), 1)
        self.assertEqual(response.json()["data"][0]["slug"], "g1")

    def test_get_group(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1", margin_pct=50)
        response = self.client.get(
            f"/api/v1/platform/groups/{g.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "g1")

    def test_update_group(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1", margin_pct=50)
        response = self.client.patch(
            f"/api/v1/platform/groups/{g.id}",
            data=json.dumps({"margin_pct": 70.0}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["margin_pct"], 70.0)

    def test_delete_group_archives(self):
        g = Group.objects.create(tenant=self.tenant, name="G1", slug="g1")
        response = self.client.delete(
            f"/api/v1/platform/groups/{g.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.status, "archived")

    def test_get_nonexistent_group_returns_404(self):
        import uuid
        response = self.client.get(
            f"/api/v1/platform/groups/{uuid.uuid4()}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 404)

    def test_tenant_isolation(self):
        """Groups from another tenant should not be visible."""
        other_tenant = Tenant.objects.create(
            name="Other", products=["metering"]
        )
        Group.objects.create(tenant=other_tenant, name="Secret", slug="secret")
        Group.objects.create(tenant=self.tenant, name="Mine", slug="mine")
        response = self.client.get(
            "/api/v1/platform/groups",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "mine")
