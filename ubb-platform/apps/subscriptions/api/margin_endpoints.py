from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router

from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, role_floor
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from core.exceptions import MisalignedAmount
from core.money import SUPPORTED_CURRENCIES, assert_aligned
from core.problems import Problem, ProblemOut
from core.time_windows import REPORT_WINDOW_MAX_DAYS, closed_months
from core.vocabulary import (
    AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED, PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN, RECOGNITION_METHOD_VALUES, REVENUE_BASIS_VALUES)
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.alerting import flagged_in
from apps.subscriptions.economics.models import (
    MarginThresholdConfig, TenantSuppliedRevenue)
from apps.subscriptions.economics.revenue import (
    DEFAULT_REVENUE_BASIS, SuppliedRevenueService)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.api.margin_schemas import (
    MarginThresholdIn, MarginThresholdOut, UnprofitableOut, BusinessMarginOut,
    RevenueBasis, SuppliedRevenueWindowOut, TenantSuppliedRevenueIn,
    TenantSuppliedRevenueOut)

margin_router = Router(auth=ApiKeyAuth())
_product_check = ProductAccess("metering")


def _current_month():
    today = timezone.now().date()
    start = today.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1)
           if start.month == 12 else start.replace(month=start.month + 1, day=1))
    return start, end


def _window(start_date, end_date):
    if start_date and end_date:
        if end_date < start_date:
            raise Problem(
                "validation_error", "end_date must not precede start_date"
            )
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem(
                "validation_error", "date window must not exceed 366 days"
            )
        return start_date, end_date
    s, _ = _current_month()
    today = timezone.now().date()
    return s, today + timedelta(days=1)  # month-to-date (inclusive of today)


# THE TENANT-WIDE MARGIN TOTAL AND THE GROUPED MARGIN BREAKDOWN WERE HERE AND
# ARE GONE (#501, slice 7 §1) — two of the nine routes the one economic query
# replaces, and two of the five backend definitions of revenue and margin it
# leaves as one.
#
# The total was the DEGENERATE CASE of that query — three money measures, no
# grouping, no bucket — computed here by a loop that read a per-customer cost
# rollup and added two more reads per customer to it. The breakdown was a
# DUPLICATE of the metering rollup a different product already served: the same
# rows and the same arithmetic over a silently different revenue basis, which is
# how one period got two margin figures. Both are now
# `GET /metering/analytics/economics`, the total with no `group_by` and the
# breakdown with one.
#
# ⚠ AND THE COUNT OF UNPROFITABLE CUSTOMERS DID NOT DIE WITH THE TOTAL. It is
# read from the alerting record, never from a margin figure, so it belongs with
# the alerting surfaces that keep their own contracts (slice 7 §8, §14) — it is
# below, on `/unprofitable`, and
# `api/v1/tests/test_the_collapse_and_what_survived_it.py` is what says so from
# outside.


@margin_router.get("/unprofitable", response=UnprofitableOut)
@role_floor(READ)
def margin_unprofitable(request, period_start: date = None):
    # THE CUSTOMERS A THRESHOLD RULE HAS NAMED, AND THE FIGURES IT NAMED THEM
    # ON — read through the alerting record's own door since #502 (slice 7 §8).
    # The route, its floor, its parameters and every figure below are unchanged;
    # what changed is that the rows come from `economics.alerting` rather than
    # from a queryset written here, which is what makes "no REPORTING surface
    # reads a margin figure from the snapshot" checkable rather than a list of
    # files somebody remembered to exempt.
    #
    # The margins here are facts about ALARMS — what each customer's flag was
    # raised on, which is what the tenant was sent a webhook about — and not
    # what that period's margin reads today. The second question is a report and
    # it is `GET /metering/analytics/economics`.
    #
    # ⚠ A COMMENT AND NOT A DOCSTRING, DELIBERATELY. django-ninja publishes a
    # view's docstring as the operation's `description`, so writing this one
    # would have put a maintainer's note about a refactor on the contract every
    # tenant reads — and taken the console snapshot and the generated SDK with
    # it, for prose that says nothing a caller needed. The operation had no
    # description before this commit and has none after it.
    _product_check(request)
    ps = period_start or _current_month()[0]
    rows = flagged_in(request.auth.tenant.id, ps)
    return {"period_start": ps.isoformat(), "customers": [{
        "customer_id": r["customer_id"], "external_id": r["external_id"],
        "gross_margin_micros": r["gross_margin_micros"],
        # A CEILING ON A MARGIN CAN ONLY GET WORSE, WHICH IS WHY THIS LIST OF
        # ALL PLACES CARRIES THE COUNT (#328). The customers here are named as
        # unprofitable on a margin computed from a cost total that excluded
        # events — the true margin is lower still, so a non-zero count never
        # means "maybe they are fine".
        UNRESOLVED_EVENT_COUNT_KEY: r[UNRESOLVED_EVENT_COUNT_KEY],
        # ⚠ AND THIS COUNT POINTS THE OTHER WAY, WHICH IS WHY IT IS HERE (#351).
        # An excluded PRICE means revenue was left out, so the true margin is
        # HIGHER than the one that named this customer unprofitable — a non-zero
        # count here really can mean "maybe they are fine", and a list of
        # unprofitable customers that showed only the count which cannot say
        # that would be the more misleading of the two.
        UNPRICED_EVENT_COUNT_KEY: r[UNPRICED_EVENT_COUNT_KEY],
        # Floated HERE rather than in the alerting read, which keeps the
        # percentage a `Decimal` all the way to the wire: the threshold
        # comparison that raised these flags is an exact one, and a customer
        # sitting on its tenant's threshold would land on the wrong side of it
        # if the evaluator read a float.
        "margin_percentage": float(r["margin_pct"]),
    } for r in rows]}


@margin_router.get("/threshold", response=MarginThresholdOut)
@role_floor(READ)
def get_threshold(request):
    _product_check(request)
    cfg = MarginThresholdConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"min_margin_pct": 0.0, "consecutive_periods": 1, "provider_cost_spike_pct": 25.0}
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_router.put("/threshold", response=MarginThresholdOut)
@role_floor(ADMIN)
@records_audit("margin_threshold.set")
def put_threshold(request, payload: MarginThresholdIn):
    _product_check(request)
    with transaction.atomic():
        cfg, _ = MarginThresholdConfig.objects.update_or_create(
            tenant=request.auth.tenant, customer=None,
            defaults={"min_margin_pct": payload.min_margin_pct,
                      "consecutive_periods": payload.consecutive_periods,
                      "provider_cost_spike_pct": payload.provider_cost_spike_pct})
        audit_record(
            action="margin_threshold.set", tenant_id=request.auth.tenant.id,
            resource_type="margin_threshold", resource_id=cfg.id,
            metadata={"min_margin_pct": float(cfg.min_margin_pct),
                      "consecutive_periods": cfg.consecutive_periods,
                      "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)})
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


# --- Tenant-supplied revenue (#495, slice 7 §9) -----------------------------
#
# WHAT A TENANT THAT BILLS ITS CUSTOMERS SOMEWHERE ELSE EARNED, stated by the
# tenant per customer per period and admitted for analytics. #153 §3.2 rules
# that both postures survive — cost tracking alone, and cost tracking plus a
# supplied figure — and the recurring profile whose pair stood above these two
# until #496 was carrying the second one badly. These two operations are what
# make it explicit, and they are now the only way to state the figure.
#
# ⚠ THE FLOORS ARE ARGUED FROM THIS MODULE'S OWN PRECEDENT, not guessed. Every
# mutating operation here is already `role_floor(ADMIN)` and every read is
# `role_floor(READ)`; a record that writes numbers appearing in margin
# reporting is an administrative act by that standard. #153 §19 handed the
# authorization model forward and #155 §16 did not take it back, so the
# argument is made here because this is the last place left to make it.
#
# ⚠ AND NEITHER OPERATION MAY EVER PRESENT ONE AS A CHARGE. UBB neither
# created nor invoiced this money — `pricing.Charge` is what UBB charged for a
# delivered piece of work, and the two records never meet.
SUPPLIED_REVENUE_PATH = "/customers/{customer_id}/supplied-revenue"


def _supplied_record_body(record):
    """One supplied record on the wire, source reference included.

    The source reference travels to every consuming surface from here: it is
    what lets a reader of a revenue number say where the number came from,
    which is the fact the recurring profile destroyed by summing its amount
    into the same column as a Stripe subscription.
    """
    return {
        "id": str(record.id),
        "amount_micros": record.amount_micros,
        "currency": record.currency,
        "period_start": record.period_start.isoformat(),
        "period_end": record.period_end.isoformat() if record.period_end else None,
        "recognition_method": record.recognition_method,
        "source_reference": record.source_reference,
        "recorded_at": record.created_at.isoformat(),
    }


@margin_router.post(
    SUPPLIED_REVENUE_PATH,
    response={200: TenantSuppliedRevenueOut, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED)
def record_supplied_revenue(request, customer_id: UUID,
                            payload: TenantSuppliedRevenueIn):
    """Record what one customer paid you for one period, billed somewhere UBB
    cannot see.

    **The figure is the whole revenue for that customer and that period — not
    an addition to what UBB priced.** Where UBB also priced the customer's usage
    inside the period, `/metering/analytics/economics` states this figure as
    the revenue and leaves that usage's price out of it, and usage nobody
    priced there no longer makes the revenue incomplete. A Stripe subscription
    is added as before and is not affected.

    `period_end` is exclusive. Omit it for revenue that is an instant rather
    than a span: such a figure covers no period, so it is counted beside the
    usage in the window it lands in rather than instead of it. Recording again
    for the same customer, `period_start` and `source_reference` re-states the
    figure; a different `source_reference` records a second figure beside it,
    and figures whose periods overlap both count — two invoices covering one
    month are two facts.
    """
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    try:
        period_start = date.fromisoformat(payload.period_start)
        period_end = (date.fromisoformat(payload.period_end)
                      if payload.period_end else None)
    except ValueError as e:
        raise Problem("validation_error", f"invalid period date: {e}")
    if period_end is not None and period_end <= period_start:
        raise Problem(
            "validation_error",
            "period_end is exclusive and must fall after period_start; "
            "omit it for revenue that is an instant rather than a span")
    if payload.recognition_method not in RECOGNITION_METHOD_VALUES:
        raise Problem(
            "validation_error",
            f"unknown recognition_method {payload.recognition_method!r}; "
            f"allowed: {', '.join(sorted(RECOGNITION_METHOD_VALUES))}")
    # A span to divide by is what the spreading method MEANS. Refused here as
    # well as at the database so the caller is told which of the two fields to
    # change, rather than meeting an integrity error that names a constraint.
    if (period_end is None
            and SuppliedRevenueService.spreads_across_a_span(
                payload.recognition_method)):
        raise Problem(
            "validation_error",
            f"recognition_method {payload.recognition_method!r} spreads the "
            "amount across a span, so period_end is required")
    source_reference = payload.source_reference.strip()
    if not source_reference:
        raise Problem(
            "validation_error",
            "source_reference says where the number came from and may not be "
            "blank — it is part of what makes the figure readable")
    currency = payload.currency.strip().lower()
    if currency not in SUPPORTED_CURRENCIES:
        raise Problem(
            "unsupported_currency",
            f"unsupported currency {currency!r}; allowed: "
            f"{', '.join(sorted(SUPPORTED_CURRENCIES))}")
    try:
        assert_aligned(payload.amount_micros, currency)
    except MisalignedAmount as misaligned:
        raise Problem("validation_error", str(misaligned))

    with transaction.atomic():
        # RE-STATING A FIGURE IS THE SAME ACT PERFORMED AGAIN, which is what
        # the record's uniqueness key means: one row per customer per
        # period-open per source reference. A different source reference for
        # the same period adds a figure BESIDE this one, because two invoices
        # covering one month are two facts rather than a contradiction.
        record, _ = TenantSuppliedRevenue.objects.update_or_create(
            tenant=request.auth.tenant, customer=customer,
            period_start=period_start, source_reference=source_reference,
            defaults={"amount_micros": payload.amount_micros,
                      "currency": currency,
                      "period_end": period_end,
                      "recognition_method": payload.recognition_method})
        audit_record(
            action=AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED,
            tenant_id=request.auth.tenant.id,
            resource_type="tenant_supplied_revenue", resource_id=record.id,
            metadata={"customer_id": str(customer.id),
                      "amount_micros": record.amount_micros,
                      "currency": record.currency,
                      "period_start": record.period_start.isoformat(),
                      "period_end": (record.period_end.isoformat()
                                     if record.period_end else None),
                      "recognition_method": record.recognition_method,
                      "source_reference": record.source_reference})
    _the_period_it_states_is_stale(record)
    return _supplied_record_body(record)


def _the_period_it_states_is_stale(record):
    """Rebuild a closed month's cached economics when a tenant states its
    revenue late (#502, slice 7 §8).

    A tenant that bills its customers elsewhere may supply a figure about a
    month that closed long ago, and **revenue is half of every margin the
    evaluator flags on** — so without this a customer could stay named
    unprofitable on the half of the answer UBB happened to have first, with the
    webhook already sent and nothing left that would ever look again.

    ⚠ **THE MARKER TABLE IS METERING'S AND THIS IS SUBSCRIPTIONS**, so it is
    asked through the metering read contract rather than reached for (ADR-001).
    That is also the honest shape: one channel says *this customer's month is
    stale*, whatever made it stale, and one consumer rebuilds it.

    ⚠ **EVERY CLOSED MONTH THE RECORD'S SPAN TOUCHES, NOT THE ONE IT OPENS
    IN.** The margin surfaces read supplied revenue under the RECOGNISED basis
    (`economics/services.py:MARGIN_REVENUE_BASIS`), and a spreading recognition
    method puts part of the amount in every month of the span — so a record
    covering a quarter, supplied today, leaves two of its three months stale at
    any age if only the first is marked. `closed_months` is where that rule is
    stated; a record that is an instant rather than a span declares no
    `period_end` and names one month or none.

    ⚠ **OUTSIDE THE WRITE'S TRANSACTION, DELIBERATELY.** The figure is recorded
    and audited whether or not a cache rebuild is queued; a marker is a request,
    and a request that could fail the statement it follows would make a
    reporting convenience able to refuse a tenant's own record.
    """
    from apps.metering.queries import mark_backfill_dirty_period

    for period_start in closed_months(record.period_start, record.period_end,
                                      now=timezone.now()):
        mark_backfill_dirty_period(record.tenant_id, record.customer_id,
                                   period_start)


@margin_router.get(
    SUPPLIED_REVENUE_PATH,
    response={200: SuppliedRevenueWindowOut, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(READ)
def get_supplied_revenue(request, customer_id: UUID, start_date: date = None,
                         end_date: date = None,
                         basis: Optional[RevenueBasis] = None):
    """The window's supplied revenue, under a basis the response names.

    ⚠ **THE BASIS PARAMETER CARRIES ITS CONCEPT'S MARKER, which is the
    OPPOSITE of the ruling on the unit-of-work listing's `status` filter**
    (`tests/contracts/test_openapi_known_values.py`), and the difference is
    worth stating because the two look alike. There the marker was declined
    because it would have NARROWED what a caller may send — turning a mistyped
    filter into a 422 where it was an empty page. Here the route already
    refuses a basis the registry does not declare, below, and would have to:
    there is no honest answer to "state this figure on a basis I have
    invented". So the marker documents a refusal the server already makes
    rather than introducing one, which is exactly when ADR-0007 §3 wants it.

    **`known` MEANS A SUPPLIED FIGURE IS ATTRIBUTABLE TO THIS WINDOW, NOT THAT
    THE WINDOW IS FULLY COVERED.** That is a real limit and it is stated rather
    than papered over: UBB cannot tell a month the tenant has not got round to
    supplying from a month in which the customer generated nothing, so "fully
    covered" is not a fact available to it. What the caller gets instead is the
    contributing records themselves, each with its own period — so the coverage
    is readable from the answer rather than asserted by a status that cannot
    know it.
    """
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    # ⚠ `DEFAULT_REVENUE_BASIS` IS THIS ROUTE'S FALLBACK AND IT IS NOT THE ONLY
    # BASIS IN THE SYSTEM. This route lets a caller CHOOSE and names what it
    # served, so its fallback is the view that invents nothing. The margin
    # surfaces this module used to carry chose nothing and published no basis
    # field, so they honoured each record's own recognition method instead —
    # the constant that says so lives in `services.py`, which argues it where
    # it is set, and the one economic query (#501) took over the choosing and
    # names what it served on every answer.
    chosen = basis or DEFAULT_REVENUE_BASIS
    if chosen not in REVENUE_BASIS_VALUES:
        raise Problem(
            "validation_error",
            f"unknown basis {chosen!r}; allowed: "
            f"{', '.join(sorted(REVENUE_BASIS_VALUES))}")
    start, end = _window(start_date, end_date)
    records = SuppliedRevenueService.in_window(
        request.auth.tenant.id, customer.id, start, end, chosen)

    rows, per_currency = [], {}
    for record in records:
        attributed = SuppliedRevenueService.attributed_micros(
            record, start, end, chosen)
        rows.append({**_supplied_record_body(record),
                     "attributed_amount_micros": attributed})
        per_currency[record.currency] = per_currency.get(record.currency, 0) + attributed
    # AN EMPTY LIST IS HOW `unknown` IS SERVED AND IT IS NEVER A ZERO. A tenant
    # that supplied nothing covering this window has revenue UBB does not know,
    # so margin is unavailable here rather than nil (#153 §3.4).
    return {
        "basis": chosen,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "pricing_status": PRICING_STATUS_KNOWN if records else PRICING_STATUS_UNKNOWN,
        "totals": [{"currency": currency, "amount_micros": per_currency[currency]}
                   for currency in sorted(per_currency)],
        "records": rows,
    }


# THE CUSTOMER-LEVEL REVENUE SWITCH'S `GET`/`PUT` PAIR WAS HERE AND IS GONE
# (#497, slice 7 §9) — ONE PATH, TWO OPERATIONS, which with the recurring
# profile's pair (#496) completes phase A's two paths and four operations
# (§17). It read and wrote a per-customer override of whether that customer's
# usage counted as revenue, and the module's own composition then obeyed it.
# Nothing replaces it, because nothing should: the question it answered coarsely
# is answered precisely, per posting, by the price status the resolver writes
# (#147 §7). The audit action the `PUT` raised is retired with it, named here
# descriptively because its G7 ledger entry is paid in this same commit and a
# swept backend file may not spell the word afterwards.


@margin_router.get("/business/{external_id}", response=BusinessMarginOut)
@role_floor(READ)
def business_margin(request, external_id: str, start_date: date = None, end_date: date = None):
    _product_check(request)
    biz = get_object_or_404(Customer, tenant=request.auth.tenant,
                            external_id=external_id, account_type="business")
    s, e = _window(start_date, end_date)
    return MarginService.compute_business(request.auth.tenant.id, biz, s, e)


# THE PER-CUSTOMER MARGIN LIST, ONE CUSTOMER'S MARGIN AND ONE CUSTOMER'S
# MARGIN TREND WERE HERE AND ARE GONE (#501, slice 7 §1) — three more of the
# nine, and with the two above this module gives up five of them.
#
# The list is `group_by=field:customer` on the one query with the revenue
# measures asked for; one customer's margin is the same question with
# `customer_id=` as a filter; and the trend is `bucket=month`. ⚠ THE TREND ALSO
# STOPS READING THE ALERTING SNAPSHOT, which is the point of it rather than a
# side effect: a stored figure is a cache of facts that move when a supplier
# cost resolves late, and a reporting surface reading one publishes a number UBB
# already knows is wrong (slice 7 §8). The one query derives every point at read
# time.
#
# What the business rollup above keeps is a TREE, and that is why it is still
# here: per-seat rows nested under a business are a different shape from a
# group-by table, and giving the table a customer axis does not produce one.
