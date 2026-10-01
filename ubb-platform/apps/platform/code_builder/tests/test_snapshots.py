"""A snapshot is the content its fingerprint is the hash of, and never moves
(#576).

Two claims the model makes and the database is held to. The content, the
fingerprint and the tenant are declared FROZEN, and a declaration is not
enforcement (ADR-0007 §2) — so each is driven through all three doors a write
can come through, and each refusal is asserted by the words it says rather
than by something having refused. And deleting one is NOT refused, because a
snapshot is prunable and leaves by cascade.

The route's behaviour — what is resolved, what a consumer reads back — is
``api/v1/tests/test_the_integration_blueprint.py``'s. This module is about the
record.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.platform.code_builder import snapshots
from apps.platform.code_builder.models import BlueprintSnapshot
from apps.platform.tenants.models import Tenant
from core.transitions import FROZEN

CONTENT = {"blueprint": {"readiness": "complete"}, "configuration": {}}
OTHER_CONTENT = {"blueprint": {"readiness": "blocked"}, "configuration": {}}


class TheFingerprintIsOfTheContentTest(TestCase):
    def test_it_is_the_named_hash_and_64_hex_characters(self):
        fingerprint = snapshots.fingerprint_of(CONTENT)

        self.assertRegex(fingerprint, r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(snapshots.is_a_fingerprint(fingerprint))

    def test_the_order_content_was_built_in_does_not_move_it(self):
        self.assertEqual(
            snapshots.fingerprint_of({"a": 1, "b": {"c": 2, "d": [1, 2]}}),
            snapshots.fingerprint_of({"b": {"d": [1, 2], "c": 2}, "a": 1}))

    def test_a_list_is_ordered_so_its_order_is_content(self):
        self.assertNotEqual(snapshots.fingerprint_of({"calls": [1, 2]}),
                            snapshots.fingerprint_of({"calls": [2, 1]}))

    def test_a_name_outside_ascii_is_hashed_as_itself(self):
        """Not as an escape of itself: the canonical bytes are UTF-8, so the
        hash can be reproduced from the content by anything that can write
        JSON."""
        self.assertIn("é".encode("utf-8"), snapshots.canonical({"k": "café"}))
        self.assertNotEqual(snapshots.fingerprint_of({"k": "café"}),
                            snapshots.fingerprint_of({"k": "cafe"}))

    def test_a_value_json_cannot_say_is_refused_rather_than_hashed(self):
        with self.assertRaises(ValueError):
            snapshots.fingerprint_of({"amount": float("nan")})


class StoringIsIdempotentAndPerTenantTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.other = Tenant.objects.create(name="O", products=["metering"])

    def test_the_same_content_is_kept_once(self):
        first = snapshots.store(tenant=self.tenant, content=CONTENT)
        second = snapshots.store(tenant=self.tenant, content=dict(CONTENT))

        self.assertEqual(first, second)
        self.assertEqual(first, snapshots.fingerprint_of(CONTENT))
        self.assertEqual(BlueprintSnapshot.objects.count(), 1)

    def test_what_is_read_back_is_what_was_kept(self):
        fingerprint = snapshots.store(tenant=self.tenant, content=CONTENT)

        self.assertEqual(
            snapshots.stored(tenant=self.tenant,
                             configuration_fingerprint=fingerprint), CONTENT)

    def test_one_tenants_snapshot_is_not_anothers(self):
        fingerprint = snapshots.store(tenant=self.tenant, content=CONTENT)

        self.assertIsNone(snapshots.stored(
            tenant=self.other, configuration_fingerprint=fingerprint))
        # And the same content under the other tenant is a row of its own.
        self.assertEqual(
            snapshots.store(tenant=self.other, content=CONTENT), fingerprint)
        self.assertEqual(BlueprintSnapshot.objects.count(), 2)

    def test_something_that_is_not_a_fingerprint_names_nothing(self):
        snapshots.store(tenant=self.tenant, content=CONTENT)

        for value in ("", "sha256:", "sha256:" + "g" * 64, None, 7):
            with self.subTest(value=value):
                with self.assertNumQueries(0):
                    self.assertIsNone(snapshots.stored(
                        tenant=self.tenant, configuration_fingerprint=value))

    def test_the_table_refuses_a_fingerprint_of_the_wrong_shape(self):
        """The shape is a fact about the column, so the database holds it for
        a write that did not come through `store`."""
        with self.assertRaisesRegex(
                IntegrityError, "ck_blueprint_snapshot_fingerprint_shape"):
            with transaction.atomic():
                BlueprintSnapshot.objects.create(
                    tenant=self.tenant, configuration_fingerprint="md5:abc",
                    content=CONTENT)

    def test_the_table_refuses_a_second_row_under_one_fingerprint(self):
        """What makes storing idempotent under a race: the loser meets this."""
        fingerprint = snapshots.store(tenant=self.tenant, content=CONTENT)

        with self.assertRaisesRegex(IntegrityError,
                                    "uq_blueprint_snapshot_fingerprint"):
            with transaction.atomic():
                BlueprintSnapshot.objects.create(
                    tenant=self.tenant,
                    configuration_fingerprint=fingerprint, content=CONTENT)


class ASnapshotNeverChangesTest(TestCase):
    """Each declared column, through each of the three doors."""

    #: What every refusal here must say: the class, and the record.
    REFUSAL = "declared frozen.*blueprint snapshot"

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.other = Tenant.objects.create(name="O", products=["metering"])
        snapshots.store(tenant=self.tenant, content=CONTENT)
        self.snapshot = BlueprintSnapshot.objects.get()
        self.moves = {
            "content": OTHER_CONTENT,
            "configuration_fingerprint":
                snapshots.fingerprint_of(OTHER_CONTENT),
            "tenant_id": self.other.id,
        }

    def _refused(self, write):
        with self.assertRaisesRegex(IntegrityError, self.REFUSAL):
            with transaction.atomic():
                write()
        held = BlueprintSnapshot.objects.get()
        self.assertEqual(
            (held.tenant_id, held.configuration_fingerprint, held.content),
            (self.tenant.id, snapshots.fingerprint_of(CONTENT), CONTENT))

    def test_the_declaration_names_exactly_the_columns_driven_here(self):
        """So a column declared later cannot go undriven by this module."""
        self.assertEqual(BlueprintSnapshot.transition_classes,
                         {column: FROZEN for column in self.moves})

    def test_save_is_refused(self):
        for column, value in self.moves.items():
            with self.subTest(column=column):
                moved = BlueprintSnapshot.objects.get()
                setattr(moved, column, value)
                self._refused(moved.save)

    def test_a_queryset_update_is_refused(self):
        for column, value in self.moves.items():
            with self.subTest(column=column):
                self._refused(lambda: BlueprintSnapshot.objects.filter(
                    pk=self.snapshot.pk).update(**{column: value}))

    def test_raw_sql_is_refused(self):
        field = BlueprintSnapshot._meta.get_field
        for column, value in self.moves.items():
            with self.subTest(column=column):
                prepared = field(
                    "tenant" if column == "tenant_id" else column
                ).get_db_prep_value(value, connection)

                def write(column=column, prepared=prepared):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"UPDATE ubb_blueprint_snapshot SET {column} = %s "
                            f"WHERE id = %s", [prepared, self.snapshot.pk])
                self._refused(write)

    def test_a_write_that_moves_none_of_them_is_admitted(self):
        """A full save rewrites every column with what it loaded and refreshes
        `updated_at`. Nothing declared moved, so nothing is refused."""
        before = self.snapshot.updated_at

        self.snapshot.save()

        self.snapshot.refresh_from_db()
        self.assertGreater(self.snapshot.updated_at, before)
        self.assertEqual(self.snapshot.content, CONTENT)

    def test_a_snapshot_may_be_deleted(self):
        """Prunable: by a row delete, and by the cascade from its tenant."""
        BlueprintSnapshot.objects.filter(pk=self.snapshot.pk).delete()
        self.assertEqual(BlueprintSnapshot.objects.count(), 0)

        snapshots.store(tenant=self.other, content=CONTENT)
        Tenant.objects.filter(pk=self.other.pk).delete()
        self.assertEqual(BlueprintSnapshot.objects.count(), 0)
