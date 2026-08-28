from django.db import IntegrityError
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import Posting, Refund


class PostingModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_1",
        )

    def test_create_event(self):
        event = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_abc123",
            billed_cost_micros=500_000,
        )
        self.assertEqual(event.billed_cost_micros, 500_000)
        self.assertEqual(event.idempotency_key, "idem_abc123")
        self.assertIsNotNone(event.effective_at)

    def test_event_immutability_save(self):
        event = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_abc123",
            billed_cost_micros=500_000,
        )
        event.billed_cost_micros = 999_999
        with self.assertRaises(ValueError):
            event.save()

    def test_event_immutability_delete(self):
        event = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_abc123",
            billed_cost_micros=500_000,
        )
        with self.assertRaises(ValueError):
            event.delete()

    def test_new_fields_have_defaults(self):
        event = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_defaults",
            billed_cost_micros=500_000,
        )
        assert event.currency == "usd"
        assert event.grouping_field_1 == ""
        # The nameless inline quantity that used to be asserted here retired in
        # #272 — the column and every reader of it. Proved as an absence by
        # `tests/contracts/test_the_inline_unit_total_is_gone.py`, which is the
        # right subject for it: the ruling is about readers across four
        # surfaces, not about one model's defaults.

    def test_idempotency_constraint(self):
        Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_duplicate",
            billed_cost_micros=500_000,
        )
        with self.assertRaises(IntegrityError):
            Posting.objects.create(
                tenant=self.tenant,
                customer=self.customer,
                idempotency_key="idem_duplicate",
                billed_cost_micros=300_000,
            )

    def test_the_posting_prints_the_identifier_it_was_given(self):
        posting = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_str",
            billed_cost_micros=500_000,
        )

        self.assertEqual(str(posting), "Posting(idem_str: 500000)")


class RefundModelTest(TestCase):
    """The refund's string reads a field on its PARENT, which is why it lives
    here rather than only in `test_posting_rename.py`.

    #269 renamed the parent and the foreign key pointing at it, and this is the
    one assertion in that change that spells the identifier field by name. The
    field it named was a retired term under a spread ceiling until #411 deleted
    it; the string now reads the idempotency key, which is the only correlation
    identity UBB has and is free to spell anywhere. The division of labour is
    unchanged and was never about the ceiling alone: the VALUE is asserted here,
    beside the model, and the rename module proves only the traversal.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="user_1")

    def test_the_refunds_string_resolves_against_its_parent(self):
        posting = Posting.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            idempotency_key="idem_refunded",
            billed_cost_micros=500_000,
        )
        refund = Refund.objects.create(
            tenant=self.tenant, customer=self.customer, posting=posting,
            amount_micros=500_000)

        self.assertEqual(str(refund), "Refund(idem_refunded: 500000)")
