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
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import TaskType
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_SUPPLIER_COGS, PRICING_MODE_FIXED,
    TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

#: `domain-vocabulary/concepts/` at the git root — the registry. Four parents
#: up: tests -> v1 -> api -> ubb-platform -> the root.
REGISTRY_CONCEPTS = Path(__file__).resolve().parents[4] / "domain-vocabulary" / "concepts"

#: The three money measures, in the order a reader thinks about them.
MONEY_MEASURES = (ANALYTICS_MEASURE_SUPPLIER_COGS,
                  ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                  ANALYTICS_MEASURE_GROSS_MARGIN)


def tenant_wide_money(tenant_id, *, start_date, end_date):
    """This tenant's ungrouped economic answer, as ``{measure: entry}``.

    ⚠ **SHARED BECAUSE TWO MODULES ASK IT AND ONE IMPORTS THE OTHER.** Both are
    about the projected Charge — one that it reaches the rails as a posting, one
    that it counts as revenue and not as work — and both read a tenant-wide
    total. Until #501 they read the daily revenue rollup; that rollup went with
    the routes it served, and the one economic query answers the same question.
    A copy in each module would be a copy of the sentinel argument below, which
    is the one thing a caller must not get wrong.

    ⚠ `contributed_revenue=()` IS A STATEMENT AND NOT A DEFAULT. The query
    refuses a revenue measure without the rows this product does not hold, so an
    empty sequence is how a fixture says *this tenant has no subscription and
    supplied nothing* — which is what makes the totals readable as postings
    alone. Passing nothing at all raises, deliberately.
    """
    from apps.metering.queries import EconomicFilters, economics

    answer = economics(
        str(tenant_id), measures=MONEY_MEASURES, contributed_revenue=(),
        filters=EconomicFilters(start_date=start_date, end_date=end_date))
    assert len(answer["rows"]) == 1, answer["rows"]
    return {entry["measure"]: entry for entry in answer["rows"][0]["measures"]}


#: The one economic query's published path.
ECONOMICS = "/api/v1/metering/analytics/economics"


def a_tenant(name="T", *, fields=()):
    """A metering tenant and a raw key for it.

    `products=["metering"]` is not optional — the one query is product-gated, so
    a tenant without it answers 403 rather than 200, which reads as an auth bug.

    ⚠ **SHARED SINCE #502, WHICH IS WHEN A SECOND MODULE ASKED THE ONE QUERY
    THROUGH THE ROUTE.** The collapse's own module built this; the module about
    a closed period restating needs the same tenant and the same key, and
    scaffolding a second one by hand is what `docs/conventions/testing.md` calls
    out by name.
    """
    from apps.platform.grouping_fields.models import GroupingField

    tenant = Tenant.objects.create(name=name, products=["metering"])
    for position, key in enumerate(fields, start=1):
        GroupingField.objects.create(tenant=tenant, key=key,
                                     slot=f"grouping_field_{position}",
                                     scope="event")
    _, raw_key = TenantApiKey.create_key(tenant)
    return tenant, raw_key


def ask(raw_key, **params):
    """One economic question, with the measures and axes repeated properly.

    A list value becomes a repeated query parameter rather than a comma-joined
    one, which is the shape the route declares and the only shape that carries
    an axis order.
    """
    from django.test import Client

    query = []
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            query += [(name, entry) for entry in value]
        elif value is not None:
            query.append((name, value))
    return Client().get(ECONOMICS, query,
                        HTTP_AUTHORIZATION=f"Bearer {raw_key}")


def measure_of(body, measure, row=0):
    """One measure's entry out of a row of the answer, or a readable failure."""
    for entry in body["rows"][row]["measures"]:
        if entry["measure"] == measure:
            return entry
    raise AssertionError(f"{measure!r} is not in row {row} of the answer")


def retired_aliases(concept_file, concept):
    """The spellings the registry has RETIRED for ``concept``, read off the
    registry itself rather than spelled in a test: the sweep refuses a
    living file that names one, so the only honest source is the document
    that retired them (`<concept_file>.yaml`, the `retired_aliases` list
    under the concept). Read by a line walk rather than a YAML parser because
    the platform's lock file carries none — the list is one item per line,
    comments interleaved, ending at the next key at the list's own
    indentation. Order is the registry's."""
    text = (REGISTRY_CONCEPTS / f"{concept_file}.yaml").read_text(encoding="utf-8")
    block = text[text.index(f"\n{concept}:"):]
    start = block.index("  retired_aliases:")
    found = []
    for line in block[start:].splitlines()[1:]:
        if re.match(r"^\s*#", line) or not line.strip():
            continue
        item = re.match(r"^    - (\S+)\s*$", line)
        if item is None:
            break
        found.append(item.group(1))
    assert found, f"{concept} lists no retired spelling — suspect the walk"
    return found


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
