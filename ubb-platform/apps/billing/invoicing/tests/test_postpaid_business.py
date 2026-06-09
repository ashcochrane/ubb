import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
def test_business_aggregates_across_seats_one_line_per_seat():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1",
                              provider_cost_micros=1, billed_cost_micros=800_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2",
                              provider_cost_micros=1, billed_cost_micros=300_000)
    total, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert total == 1_100_000 and sum(a for _, a in lines) == total
    assert dict(lines)["alice"] == 800_000 and dict(lines)["bob"] == 300_000


@pytest.mark.django_db
def test_close_rolls_seats_into_one_business_invoice():
    from unittest.mock import patch, MagicMock
    from django.utils import timezone
    from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
    from apps.billing.invoicing.models import CustomerUsageInvoice
    t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="postpaid",
                              stripe_connected_account_id="acct_x")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated", stripe_customer_id="cus_biz")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    start, end = _prior_month()
    for seat, key, amt in [(s1, "i1", 800_000), (s2, "i2", 300_000)]:
        ev = UsageEvent.objects.create(tenant=t, customer=seat, request_id="r", idempotency_key=key,
                                       provider_cost_micros=1, billed_cost_micros=amt)
        UsageEvent.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
    with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
         patch("apps.platform.events.tasks.process_single_event"):
        mock_sc.return_value = MagicMock(id="obj_1")
        close_postpaid_usage_periods()
    invs = CustomerUsageInvoice.objects.filter(tenant=t)
    assert invs.count() == 1                       # ONE invoice, keyed on the business
    inv = invs.first()
    assert str(inv.customer_id) == str(biz.id) and inv.total_billed_micros == 1_100_000
    assert inv.line_items.count() == 2             # one line per seat
    assert not CustomerUsageInvoice.objects.filter(customer__in=[s1, s2]).exists()  # seats not invoiced


@pytest.mark.django_db
def test_business_total_unchanged_when_seat_soft_deleted_mid_period():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1", provider_cost_micros=1, billed_cost_micros=800_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2", provider_cost_micros=1, billed_cost_micros=300_000)
    before, _ = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    s2.soft_delete()
    after, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert after == before == 1_100_000          # FAILS today: 800_000
    assert dict(lines)["bob"] == 300_000


@pytest.mark.django_db
def test_close_invoices_soft_deleted_seat_usage():
    from unittest.mock import patch, MagicMock
    from django.utils import timezone
    from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
    from apps.billing.invoicing.models import CustomerUsageInvoice
    t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="postpaid", stripe_connected_account_id="acct_x")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="allocated", stripe_customer_id="cus_biz")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    start, _end = _prior_month()
    ev = UsageEvent.objects.create(tenant=t, customer=s1, request_id="r", idempotency_key="i1", provider_cost_micros=1, billed_cost_micros=500_000)
    UsageEvent.objects.filter(id=ev.id).update(effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
    s1.soft_delete()
    with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
         patch("apps.platform.events.tasks.process_single_event"):
        mock_sc.return_value = MagicMock(id="obj_1")
        close_postpaid_usage_periods()
    invs = CustomerUsageInvoice.objects.filter(tenant=t)
    assert invs.count() == 1                       # FAILS today: 0
    inv = invs.first()
    assert str(inv.customer_id) == str(biz.id)
    assert inv.total_billed_micros == 500_000
