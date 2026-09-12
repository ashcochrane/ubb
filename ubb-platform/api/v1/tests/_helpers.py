"""Shared setup for the composition layer's tests of work sold at one agreed
price (`docs/conventions/testing.md` — shared setup helpers live beside the
tests that use them).

ONE FIXTURE, THREE MODULES. The prepaid reservation's three modules — the
start's reservation and its refusals, the three-worker race, and the release
on every terminal path — each need the same tenant: one that sells one kind
of work whole and one per event, at both altitudes, with a price line in its
default book and a customer whose wallet holds a chosen balance. The posture
varies per module (the products, the billing mode, the switch, the balance),
so it is a function of those and nothing else; what a module does with the
tenant — which routes it drives, what it asserts — stays the module's own.
"""
import uuid
from dataclasses import dataclass

from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import TaskType
from core.vocabulary import (
    PRICING_MODE_FIXED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

#: The kind of work sold at one agreed price, and the one sold per event.
SOLD_WHOLE = "transcode"
SOLD_PER_EVENT = "chat"
THE_AGREED_PRICE = 8_000_000


@dataclass(frozen=True)
class ATenantSellingWholeWork:
    tenant: Tenant
    raw_key: str
    customer: Customer
    #: None where the posture has no wallet (a tenant that does not bill).
    wallet: Wallet | None

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def start_body(self, **body):
        """A start request for this customer's whole-work kind, with a fresh
        claim; a caller overrides whichever field its case is about."""
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("task_type", SOLD_WHOLE)
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return body


def a_tenant_selling_whole_work(*, products=("metering", "billing"),
                                billing_mode="prepaid", enforcement_mode=None,
                                balance_micros=None,
                                price_micros=THE_AGREED_PRICE,
                                name="T", external_id="c1"):
    """The fixture above, in the posture the arguments name. ``billing_mode``
    None leaves the tenant on the mode it is born with (a tenant that does
    not bill); ``balance_micros`` None creates no wallet."""
    options = {}
    if billing_mode:
        options["billing_mode"] = billing_mode
    if enforcement_mode:
        options["enforcement_mode"] = enforcement_mode
    tenant = Tenant.objects.create(name=name, products=list(products), **options)
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id=external_id)
    for kind in (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK):
        TaskType.objects.create(tenant=tenant, key=SOLD_WHOLE, kind=kind,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        TaskType.objects.create(tenant=tenant, key=SOLD_PER_EVENT, kind=kind,
                                uncapped=True)
    a_price_for_whole_work(tenant, task_type=SOLD_WHOLE,
                           amount_micros=price_micros)
    wallet = None
    if balance_micros is not None:
        wallet = Wallet.objects.create(customer=customer,
                                       balance_micros=balance_micros)
    return ATenantSellingWholeWork(tenant, raw_key, customer, wallet)
