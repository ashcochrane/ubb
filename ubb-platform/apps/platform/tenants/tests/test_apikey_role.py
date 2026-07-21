"""TenantApiKey role field (identity build 1, #79).

Every existing key must carry role Admin post-migration with byte-identical
behaviour. The mechanism is Django's ``AddField`` with ``default="admin"``, which
backfills every pre-existing row; these tests pin that default at both the model
and the migration-operation level so it can never silently regress to a
lower-authority default.
"""
import importlib

from django.test import TestCase
from django.db import migrations, models

from apps.platform.membership.roles import ADMIN
from apps.platform.tenants.models import Tenant, TenantApiKey


class ApiKeyRoleDefaultTest(TestCase):
    def test_model_field_default_is_admin(self):
        self.assertEqual(TenantApiKey._meta.get_field("role").default, ADMIN)

    def test_new_key_is_admin(self):
        tenant = Tenant.objects.create(name="Acme")
        key_obj, _ = TenantApiKey.create_key(tenant, label="k")
        self.assertEqual(key_obj.role, ADMIN)

    def test_migration_backfills_existing_rows_to_admin(self):
        # The AddField default is what Postgres writes onto every pre-existing
        # row when 0022 applies — so existing keys carry Admin post-migration.
        mig = importlib.import_module(
            "apps.platform.tenants.migrations.0022_tenantapikey_role")
        add_field = next(
            op for op in mig.Migration.operations
            if isinstance(op, migrations.AddField) and op.name == "role")
        self.assertIsInstance(add_field.field, models.CharField)
        self.assertEqual(add_field.field.default, ADMIN)
