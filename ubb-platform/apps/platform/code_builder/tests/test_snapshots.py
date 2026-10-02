"""A snapshot is what its fingerprint is the hash of, and never moves (#576).

Three claims the kernel makes and is held to here.

**The fingerprint is the hash of the identity half, and of nothing else.** A
snapshot's content is an identity and a presentation; only the first is
hashed (owner ruling of 2026-10-02). What the resolver PUTS in each half is
held through the API, in ``api/v1/tests/test_the_integration_blueprint.py``;
what is held here is that the store hashes the half it says it does.

**The content, the fingerprint and the tenant are FROZEN**, and a declaration
is not enforcement (ADR-0007 §2) — so each is driven through all three doors a
write can come through, and each refusal is asserted by the words it says
rather than by something having refused.

**Deleting one is NOT refused**, because a snapshot is prunable and leaves by
cascade.
"""
import hashlib
import json

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.platform.code_builder import snapshots
from apps.platform.code_builder.models import BlueprintSnapshot
from apps.platform.tenants.models import Tenant
from core.transitions import FROZEN

IDENTITY = {"blueprint": {"readiness": "complete"}, "configuration": {}}
OTHER_IDENTITY = {"blueprint": {"readiness": "blocked"}, "configuration": {}}
PRESENTATION = {"remediation_requests": [None]}
OTHER_PRESENTATION = {"remediation_requests": [{"route": "/somewhere/else"}]}


def _content(identity=IDENTITY, presentation=PRESENTATION):
    return {snapshots.IDENTITY: identity,
            snapshots.PRESENTATION: presentation}


class TheFingerprintIsOfTheIdentityTest(TestCase):
    def test_it_is_the_named_hash_and_64_hex_characters(self):
        fingerprint = snapshots.fingerprint_of(IDENTITY)

        self.assertRegex(fingerprint, r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(snapshots.is_a_fingerprint(fingerprint))

    def test_it_can_be_reproduced_by_anything_that_can_write_json(self):
        """Sorted keys, no insignificant whitespace, UTF-8, SHA-256 — stated
        here in full, independently of the function under test."""
        identity = {"b": [1, {"d": "é", "c": None}], "a": True}
        by_hand = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")

        self.assertEqual(by_hand, b'{"a":true,"b":[1,{"c":null,"d":"\xc3\xa9"}]}')
        self.assertEqual(snapshots.fingerprint_of(identity),
                         "sha256:" + hashlib.sha256(by_hand).hexdigest())

    def test_the_order_an_object_was_built_in_does_not_move_it(self):
        self.assertEqual(
            snapshots.fingerprint_of({"a": 1, "b": {"c": 2, "d": [1, 2]}}),
            snapshots.fingerprint_of({"b": {"d": [1, 2], "c": 2}, "a": 1}))

    def test_a_list_is_ordered_so_its_order_is_hashed(self):
        """Which is why a list whose order means nothing must arrive in a
        canonical order: this function cannot know which lists those are."""
        self.assertNotEqual(snapshots.fingerprint_of({"calls": [1, 2]}),
                            snapshots.fingerprint_of({"calls": [2, 1]}))

    def test_a_name_outside_ascii_is_hashed_as_itself(self):
        """Not as an escape of itself: the canonical bytes are UTF-8."""
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

    def _store(self, tenant=None, identity=IDENTITY,
               presentation=PRESENTATION):
        return snapshots.store(tenant=tenant or self.tenant,
                               identity=identity, presentation=presentation)

    def test_the_fingerprint_is_of_the_identity_and_not_of_the_presentation(
            self):
        fingerprint = self._store()

        self.assertEqual(fingerprint, snapshots.fingerprint_of(IDENTITY))
        self.assertNotEqual(fingerprint,
                            snapshots.fingerprint_of(_content()))
        self.assertEqual(
            self._store(self.other, presentation=OTHER_PRESENTATION),
            fingerprint)

    def test_the_same_identity_is_kept_once(self):
        first = self._store()
        second = self._store(identity=dict(IDENTITY))

        self.assertEqual(first, second)
        self.assertEqual(BlueprintSnapshot.objects.count(), 1)

    def test_an_identity_already_kept_keeps_the_presentation_it_came_with(
            self):
        """First wins. The same identity arriving with another presentation
        is the same snapshot, found, and nothing about it is rewritten."""
        fingerprint = self._store()

        self.assertEqual(self._store(presentation=OTHER_PRESENTATION),
                         fingerprint)
        self.assertEqual(BlueprintSnapshot.objects.count(), 1)
        self.assertEqual(
            snapshots.stored(tenant=self.tenant,
                             configuration_fingerprint=fingerprint),
            _content())

    def test_what_is_read_back_is_both_halves_as_they_were_kept(self):
        fingerprint = self._store(presentation=OTHER_PRESENTATION)

        self.assertEqual(
            snapshots.stored(tenant=self.tenant,
                             configuration_fingerprint=fingerprint),
            _content(presentation=OTHER_PRESENTATION))

    def test_one_tenants_snapshot_is_not_anothers(self):
        fingerprint = self._store()

        self.assertIsNone(snapshots.stored(
            tenant=self.other, configuration_fingerprint=fingerprint))
        # And the same identity under the other tenant is a row of its own.
        self.assertEqual(self._store(self.other), fingerprint)
        self.assertEqual(BlueprintSnapshot.objects.count(), 2)

    def test_something_that_is_not_a_fingerprint_names_nothing(self):
        self._store()

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
                    content=_content())

    def test_the_table_refuses_a_second_row_under_one_fingerprint(self):
        """What makes storing idempotent under a race: the loser meets this."""
        fingerprint = self._store()

        with self.assertRaisesRegex(IntegrityError,
                                    "uq_blueprint_snapshot_fingerprint"):
            with transaction.atomic():
                BlueprintSnapshot.objects.create(
                    tenant=self.tenant,
                    configuration_fingerprint=fingerprint, content=_content())


class ASnapshotNeverChangesTest(TestCase):
    """Each declared column, through each of the three doors."""

    #: What every refusal here must say: the class, and the record.
    REFUSAL = "declared frozen.*blueprint snapshot"

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.other = Tenant.objects.create(name="O", products=["metering"])
        snapshots.store(tenant=self.tenant, identity=IDENTITY,
                        presentation=PRESENTATION)
        self.snapshot = BlueprintSnapshot.objects.get()
        self.moves = {
            "content": _content(OTHER_IDENTITY),
            "configuration_fingerprint":
                snapshots.fingerprint_of(OTHER_IDENTITY),
            "tenant_id": self.other.id,
        }

    def _refused(self, write):
        with self.assertRaisesRegex(IntegrityError, self.REFUSAL):
            with transaction.atomic():
                write()
        held = BlueprintSnapshot.objects.get()
        self.assertEqual(
            (held.tenant_id, held.configuration_fingerprint, held.content),
            (self.tenant.id, snapshots.fingerprint_of(IDENTITY), _content()))

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

    def test_the_presentation_half_is_frozen_with_the_rest(self):
        """Not hashed is not the same as editable: the row is one record, and
        a Blueprint read back tomorrow is the one answered today."""
        self._refused(lambda: BlueprintSnapshot.objects.filter(
            pk=self.snapshot.pk).update(
            content=_content(presentation=OTHER_PRESENTATION)))

    def test_a_write_that_moves_none_of_them_is_admitted(self):
        """A full save rewrites every column with what it loaded and refreshes
        `updated_at`. Nothing declared moved, so nothing is refused."""
        before = self.snapshot.updated_at

        self.snapshot.save()

        self.snapshot.refresh_from_db()
        self.assertGreater(self.snapshot.updated_at, before)
        self.assertEqual(self.snapshot.content, _content())

    def test_a_snapshot_may_be_deleted(self):
        """Prunable: by a row delete, and by the cascade from its tenant."""
        BlueprintSnapshot.objects.filter(pk=self.snapshot.pk).delete()
        self.assertEqual(BlueprintSnapshot.objects.count(), 0)

        snapshots.store(tenant=self.other, identity=IDENTITY,
                        presentation=PRESENTATION)
        Tenant.objects.filter(pk=self.other.pk).delete()
        self.assertEqual(BlueprintSnapshot.objects.count(), 0)
