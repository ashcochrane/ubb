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
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from django.db.models import JSONField
from django.test import Client
from django.utils import timezone

from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.membership.roles import READ
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
    alone. Passing nothing at all raises, deliberately. `covered_periods=()` is
    the same statement about the periods a supplied figure covers (#537).
    """
    from apps.metering.queries import EconomicFilters, economics

    answer = economics(
        str(tenant_id), measures=MONEY_MEASURES,
        covered_periods=(), contributed_revenue=(),
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
    tenant = Tenant.objects.create(name=name, products=["metering"])
    for position, key in enumerate(fields, start=1):
        GroupingField.objects.create(tenant=tenant, key=key,
                                     slot=f"grouping_field_{position}",
                                     scope="event")
    _, raw_key = TenantApiKey.create_key(tenant)
    return tenant, raw_key


def a_live_client(live_server, **tenant_fields):
    """A tenant with one customer, `acme`, and the real SDK client pointed at
    the live server — what a module driving the SDK over HTTP starts from.
    `max_retries=0`, so a retry can never hide the one answer under test.
    ``tenant_fields`` sets the tenant's posture; metering-only by default.
    Returns ``(client, tenant, customer)``; the caller closes the client.

    ⚠ SHARED SINCE #569, the second module to drive the SDK against the live
    server (`test_sdk_work_block_over_the_wire.py` was the first). The SDK is
    imported here rather than at the top, so a module that never drives it
    does not come to depend on its install."""
    from ubb.metering import MeteringClient
    tenant = Tenant.objects.create(
        name="T", **{"products": ["metering"], **tenant_fields})
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    client = MeteringClient(api_key=raw_key, base_url=live_server.url,
                            max_retries=0)
    return client, tenant, customer


def ask(raw_key, **params):
    """One economic question, with the measures and axes repeated properly.

    A list value becomes a repeated query parameter rather than a comma-joined
    one, which is the shape the route declares and the only shape that carries
    an axis order.
    """
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


# ---------------------------------------------------------------------------
# An Integration Blueprint's configuration, declared through the tenant's routes
# ---------------------------------------------------------------------------
#
# SHARED SINCE #577, which is when a second module needed it: the Blueprint's
# own suite built this, and the module that holds the renderer's committed
# fixtures to what the route answers declares configuration the same way.

BLUEPRINTS = "/api/v1/code-builder/blueprints"

KIND = "report_generation"
SUBTASK_KIND = "summarise"
EVENT = "chat.completion"

INPUT_TOKENS = {"display_name": "Input tokens", "value_type": "integer",
                "unit": "token", "required_for_costing": True,
                "source_kind": "provider_response",
                "source_path": ["usage", "input_tokens"]}
SEARCHES = {"display_name": "Searches", "value_type": "integer",
            "unit": "search", "required_for_costing": False,
            "source_kind": "caller_supplied", "source_path": []}

#: A shape whose paths are read off a Python library's object, and one whose
#: paths are read off the JSON a web API returns.
A_PYTHON_SHAPE = "openai.responses.python.v1"
A_JSON_SHAPE = "google.gemini.rest.v1"

#: The supplier the complete configuration's Event Type names, and the one
#: whose default cost book `_cost_rules` writes to unless told another.
PROVIDER = "openai"


class BlueprintRoutes:
    """The tenant's own routes, and the fixtures built out of them."""

    def setup_method(self):
        self.tenant, self.raw_key = a_tenant()
        self.client = Client()

    # -- the routes --------------------------------------------------------

    def _send(self, method, path, data=None, key=None):
        auth = {"HTTP_AUTHORIZATION": f"Bearer {key or self.raw_key}"}
        if method == "get":
            return self.client.get(path, **auth)
        return getattr(self.client, method)(
            path, data=json.dumps(data or {}),
            content_type="application/json", **auth)

    def _call(self, method, path, data=None, key=None):
        response = self._send(method, path, data, key)
        assert response.status_code < 300, response.content
        return response.json() if response.content else None

    def _resolve(self, key=None, **selection):
        selection.setdefault("target", "python_sdk")
        return self._call("post", BLUEPRINTS, selection, key)

    def _a_read_key(self):
        """A key at the READ floor. Written to the row: a key's role has no
        route of its own in this module's reach, and the floor is the subject
        rather than how a key comes to have one."""
        key, raw = TenantApiKey.create_key(self.tenant, label="read-only")
        TenantApiKey.objects.filter(pk=key.pk).update(role=READ)
        return raw

    # -- the two states the tables admit and no route produces ---------------

    def _retire(self, key):
        """A Grouping Field retired. Written to the row: the registry keeps a
        retirement instant and publishes it, and no route sets one yet."""
        GroupingField.objects.filter(tenant=self.tenant, key=key).update(
            retired_at=timezone.now())

    def _require_without_declaring(self, kind, *fields):
        """A kind of work requiring Grouping Fields the registry would have
        refused. Written to the row, on the one column of a kind that holds a
        list — found by its type, so this module spells no column name."""
        (holding_the_list,) = [
            field.name for field in TaskType._meta.concrete_fields
            if isinstance(field, JSONField)]
        TaskType.objects.filter(tenant=self.tenant, key=kind).update(
            **{holding_the_list: list(fields)})

    # -- configuration, declared the way a tenant declares it ----------------

    def _grouping_fields(self, *fields):
        self._call("put", "/api/v1/metering/grouping-fields",
                   {"grouping_fields": [
                       {"key": key, "slot": f"grouping_field_{position}",
                        "scope": scope}
                       for position, (key, scope) in enumerate(fields, 1)]})

    def _kinds(self, *kinds):
        self._call("put", "/api/v1/task-types", {"task_types": list(kinds)})

    def _event_type(self, key=EVENT, *, costing_method="calculated",
                    shape=A_PYTHON_SHAPE, label="", provider=None,
                    measurements=None, mapping=None, publish=True):
        if provider:
            self._call("post", "/api/v1/providers", {"key": provider})
        self._call("post", "/api/v1/event-types",
                   {"key": key, "costing_method": costing_method,
                    "source_shape_id": shape, "source_shape_label": label,
                    "provider_key": provider})
        if measurements is None:
            measurements = {"input_tokens": INPUT_TOKENS}
        for code, declared in measurements.items():
            self._call("put",
                       f"/api/v1/event-types/{key}/measurements/"
                       f"{quote(code, safe='')}", declared)
        if mapping:
            self._call("put",
                       f"/api/v1/event-types/{key}/reported-cost-mapping",
                       mapping)
        if publish:
            return self._publish(key)
        return self._call("get", f"/api/v1/event-types/{key}")

    def _publish(self, key=EVENT):
        return self._call("post", f"/api/v1/event-types/{key}/publish")

    def _a_kind(self, key=KIND, **declared):
        declared.setdefault("uncapped", True)
        self._kinds({"key": key, **declared})

    def _complete_configuration(self):
        """One kind of work requiring one Task-scoped Grouping Field, one
        Subtask kind requiring a Subtask-scoped one, and one published Event
        Type with a supplier — everything a complete Blueprint resolves."""
        self._grouping_fields(("environment", "task"), ("phase", "subtask"))
        self._kinds(
            {"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
             "required_grouping_fields": ["environment"]},
            {"key": SUBTASK_KIND, "kind": "subtask", "uncapped": True,
             "required_grouping_fields": ["phase"]})
        return self._event_type(
            provider=PROVIDER,
            measurements={"input_tokens": INPUT_TOKENS, "searches": SEARCHES})

    def _complete(self, **selection):
        selection.setdefault("task_type", KIND)
        selection.setdefault("event_types", [EVENT])
        return self._resolve(**selection)

    # -- the books ---------------------------------------------------------
    #
    # SHARED SINCE #582, which is when a second module needed a configuration
    # whose costs are known: Verify's suite built these, and the execution
    # suite at the git root declares priced configurations the same way.

    def _cost_rules(self, *rules, provider=PROVIDER, grouping_fields=None):
        """Publish `(kind, measurement, rate per unit)` changes into the
        supplier's default cost book, declaring the book on first use."""
        books = self._call("get", "/api/v1/metering/pricing/cost-books")
        held = [book for book in books["data"]
                if book["provider_key"] == provider]
        book = held[0] if held else self._call(
            "post", "/api/v1/metering/pricing/cost-books",
            {"provider_key": provider, "key": provider, "is_default": True})
        publishes = f"/api/v1/metering/pricing/books/{book['id']}/publishes"
        draft = self._call("post", publishes, {"changes": [
            {"kind": kind, "measurement_key": code, "provider": provider,
             "grouping_fields": grouping_fields or {},
             "rate_per_unit_micros": rate, "unit_quantity": 1}
            for kind, code, rate in rules]})
        self._call("post", f"{publishes}/{draft['id']}/publish")

    def _markup(self, micro_percent):
        self._call("put", "/api/v1/metering/pricing/default-markup",
                   {"markup_micro_percent": micro_percent})
