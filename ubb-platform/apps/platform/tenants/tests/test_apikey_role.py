"""TenantApiKey role field (identity build 1, #79).

A key created without a role carries Admin — the authority every key had
before roles existed, so adding the field changed no key's behaviour. These
tests pin that default at the model so it can never silently regress to a
lower-authority one.

(Before the cutover, #190, a third case also pinned `tenants/0022`'s
`AddField` default, which is what wrote Admin onto every key that existed when
the field arrived. A fresh database has no such key; the model default below is
the same fact, and is what the initial schema is generated from.)
"""
from django.test import TestCase

from apps.platform.membership.roles import ADMIN
from apps.platform.tenants.models import Tenant, TenantApiKey


class ApiKeyRoleDefaultTest(TestCase):
    def test_model_field_default_is_admin(self):
        self.assertEqual(TenantApiKey._meta.get_field("role").default, ADMIN)

    def test_new_key_is_admin(self):
        tenant = Tenant.objects.create(name="Acme")
        key_obj, _ = TenantApiKey.create_key(tenant, label="k")
        self.assertEqual(key_obj.role, ADMIN)
