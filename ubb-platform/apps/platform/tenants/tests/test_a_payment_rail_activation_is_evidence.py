"""A payment-rail activation is immutable evidence, beside a flag that is not
(ADR-0008 §6; the owner's ruling 2).

`rail`, `environment`, `activated_at`, `approved_by` and `evidence` say who
approved which rail, where, when and on what — history, declared `FROZEN`
(ADR-0007 §2) and held by `trg_payment_rail_activation_declared_transitions`
through `save()`, `QuerySet.update()` and raw SQL alike. `enabled` is the
operational switch and moves freely: it is the control every refusal here is
measured against. There is no delete or revoke path, and the admin — the one
door an approver records an activation through — grants no delete.
"""
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.platform.tenants.models import PaymentRailActivation
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend,
    declaring_models_by_table,
)
from core.transitions import FROZEN, columns_declared_into_defended_classes
from core.vocabulary import (
    PAYMENT_RAIL_ENVIRONMENT_LIVE,
    PAYMENT_RAIL_ENVIRONMENT_TEST,
    PAYMENT_RAIL_STRIPE,
)

EVIDENCE = ("rail", "environment", "activated_at", "approved_by", "evidence")
TRIGGER = "trg_payment_rail_activation_declared_transitions"


def _recorded(**columns):
    fields = {"rail": PAYMENT_RAIL_STRIPE,
              "environment": PAYMENT_RAIL_ENVIRONMENT_LIVE,
              "activated_at": timezone.now() - timedelta(days=1),
              "approved_by": "the named approver",
              "evidence": "a controlled live transaction, reconciled once"}
    fields.update(columns)
    return PaymentRailActivation.objects.create(**fields)


#: A different value for each evidence column. All but `rail` are legal in
#: themselves, so the only thing refusing them is the freeze. The registry has
#: one rail, so no legal value can move that column at all; the freeze still
#: answers first, because a `BEFORE` row trigger runs before any `CHECK` — and
#: the assertion reads the freeze's own words, so the `CHECK`'s refusal would
#: not pass for it.
def _another(column, activation):
    return {
        "rail": "another_rail",
        "environment": PAYMENT_RAIL_ENVIRONMENT_TEST,
        "activated_at": activation.activated_at - timedelta(days=30),
        "approved_by": "somebody else",
        "evidence": "a different story",
    }[column]


class TheEvidenceIsFrozenTest(TestCase):

    def setUp(self):
        self.activation = _recorded()

    def _doors(self, column, value):
        pk = self.activation.pk

        def by_save():
            fresh = PaymentRailActivation.objects.get(pk=pk)
            setattr(fresh, column, value)
            fresh.save()

        return {
            "save()": by_save,
            "QuerySet.update()": lambda: PaymentRailActivation.objects.filter(
                pk=pk).update(**{column: value}),
            "raw SQL": lambda: connection.cursor().execute(
                f"UPDATE ubb_payment_rail_activation SET {column} = %s "
                f"WHERE id = %s", [value, str(pk)]),
        }

    def test_no_evidence_column_moves_through_any_door(self):
        for column in EVIDENCE:
            value = _another(column, self.activation)
            for door, write in self._doors(column, value).items():
                with self.subTest(column=column, door=door):
                    with self.assertRaisesRegex(
                            IntegrityError, rf"declared frozen \(ADR-0007 2\): {column}\."):
                        with transaction.atomic():
                            write()
                    stored = PaymentRailActivation.objects.get(pk=self.activation.pk)
                    self.assertEqual(getattr(stored, column),
                                     getattr(self.activation, column))

    def test_the_flag_moves_through_every_door(self):
        """THE CONTROL: the same three doors, on the column that is not
        evidence. Without it the refusals above could be a table that refuses
        every UPDATE."""
        for door, write in self._doors("enabled", False).items():
            with self.subTest(door=door):
                PaymentRailActivation.objects.filter(
                    pk=self.activation.pk).update(enabled=True)
                write()
                self.assertFalse(
                    PaymentRailActivation.objects.get(pk=self.activation.pk).enabled)

    def test_the_model_declares_the_five_and_the_database_defends_them(self):
        self.assertEqual(PaymentRailActivation.transition_classes,
                         dict.fromkeys(EVIDENCE, FROZEN))
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes([PaymentRailActivation]),
                declaring_models_by_table()),
            [])
        with connection.cursor() as cursor:
            cursor.execute("SELECT tgname FROM pg_trigger WHERE tgname = %s",
                           [TRIGGER])
            self.assertEqual(cursor.fetchone(), (TRIGGER,))


class AnActivationIsEvidenceWhenRecordedTest(TestCase):
    """What the database refuses on the way in: an activation with no named
    approver or no evidence is not evidence, and there is one per rail and
    environment so the flag's answer is never ambiguous."""

    def test_a_blank_approver_or_evidence_is_refused(self):
        for column, constraint in (
                ("approved_by", "ck_payment_rail_activation_names_its_approver"),
                ("evidence", "ck_payment_rail_activation_carries_its_evidence")):
            with self.subTest(column=column):
                with self.assertRaisesRegex(IntegrityError, constraint):
                    with transaction.atomic():
                        _recorded(**{column: ""})

    def test_an_unknown_rail_or_environment_is_refused(self):
        for column, constraint in (
                ("rail", "ck_payment_rail_activation_rail_known"),
                ("environment", "ck_payment_rail_activation_environment_known")):
            with self.subTest(column=column):
                with self.assertRaisesRegex(IntegrityError, constraint):
                    with transaction.atomic():
                        _recorded(**{column: "staging"})

    def test_one_activation_per_rail_and_environment(self):
        _recorded()

        with self.assertRaisesRegex(
                IntegrityError, "uq_payment_rail_activation_once_per_environment"):
            with transaction.atomic():
                _recorded(approved_by="a second approver")
        _recorded(environment=PAYMENT_RAIL_ENVIRONMENT_TEST)  # the other one is fine


class NoDoorDeletesAnActivationTest(TestCase):
    """"No delete or revoke path" (ruling 2) is the table's, not only the
    admin's: every door that could erase the evidence is refused, and the
    row survives. A rail is withdrawn by its flag (the freeze's control)."""

    def test_the_evidence_survives_every_door_that_deletes(self):
        activation = _recorded()
        doors = {
            "Model.delete()": lambda: PaymentRailActivation.objects.get(
                pk=activation.pk).delete(),
            "QuerySet.delete()": lambda: PaymentRailActivation.objects.filter(
                pk=activation.pk).delete(),
            "raw SQL": lambda: connection.cursor().execute(
                "DELETE FROM ubb_payment_rail_activation WHERE id = %s",
                [str(activation.pk)]),
        }
        for door, delete in doors.items():
            with self.subTest(door=door):
                with self.assertRaisesRegex(IntegrityError, "never deleted"):
                    with transaction.atomic():
                        delete()
                self.assertTrue(PaymentRailActivation.objects.filter(
                    pk=activation.pk).exists())


class TheAdminHasNoDeleteOrRevokePathTest(TestCase):
    """The admin is where an approver records an activation and turns its
    flag. It never deletes one, and never edits what was approved."""

    def setUp(self):
        self.activation = _recorded()
        self.operator = get_user_model().objects.create_superuser(
            username="operator", email="operator@example.com", password="pw")
        self.model_admin = admin.site._registry[PaymentRailActivation]
        self.request = RequestFactory().get("/")
        self.request.user = self.operator

    def test_no_delete_permission_and_no_bulk_delete_action(self):
        self.assertFalse(self.model_admin.has_delete_permission(
            self.request, self.activation))
        self.assertNotIn("delete_selected",
                         self.model_admin.get_actions(self.request))

    def test_the_delete_page_is_forbidden_and_the_row_survives(self):
        http = Client()
        http.force_login(self.operator)
        url = reverse("admin:tenants_paymentrailactivation_delete",
                      args=[self.activation.pk])

        self.assertEqual(http.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(PaymentRailActivation.objects.filter(
            pk=self.activation.pk).exists())

    def test_the_evidence_is_read_only_once_recorded_and_the_flag_is_not(self):
        read_only = set(self.model_admin.get_readonly_fields(
            self.request, self.activation))

        self.assertEqual(read_only, set(EVIDENCE))
        self.assertEqual(
            set(self.model_admin.get_readonly_fields(self.request, None)), set())
