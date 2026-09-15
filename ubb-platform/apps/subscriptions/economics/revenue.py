import calendar

from core.vocabulary import (
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE,
    REVENUE_BASIS_RECOGNISED, REVENUE_BASIS_RECORDED)

#: WHETHER EACH RECOGNITION METHOD SPREADS THE AMOUNT ACROSS THE RECORD'S OWN
#: SPAN (#495). Both methods are named rather than one tested and the other
#: inferred: a third method arriving would then raise at the single place that
#: decides, instead of quietly taking the "do not spread" half of a choice the
#: record made and this map had never been taught. The record's own check
#: constraint refuses a method outside this set, so the raise is a signal that
#: the registry moved and this did not.
_SPREADS_ACROSS_THE_SPAN = {
    RECOGNITION_METHOD_STRAIGHT_LINE: True,
    RECOGNITION_METHOD_ON_RECEIPT: False,
}

#: THE BASIS A SURFACE SERVES WHEN ITS CALLER NAMED NONE. `recorded` invents
#: nothing — it places each amount whole on the day its record opens — so a
#: caller who did not ask for a distribution never silently receives one. Every
#: response carrying a supplied revenue figure states the basis it served, so
#: the default is visible rather than assumed (slice 7 §5).
DEFAULT_REVENUE_BASIS = REVENUE_BASIS_RECORDED


def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def _month_iter(start, end):
    """Yield (month_start, month_end) calendar months overlapping [start, end)."""
    cur = start.replace(day=1)
    while cur < end:
        nxt = (cur.replace(year=cur.year + 1, month=1, day=1)
               if cur.month == 12 else cur.replace(month=cur.month + 1, day=1))
        yield cur, nxt
        cur = nxt


class RevenueService:
    @staticmethod
    def manual_revenue_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        from apps.subscriptions.economics.models import CustomerRevenueProfile
        p = CustomerRevenueProfile.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id).first()
        if not p or not p.recurring_amount_micros:
            return 0
        eff_start = max(start_date, p.effective_from)
        eff_end = end_date if p.effective_to is None else min(end_date, p.effective_to)
        if eff_end <= eff_start:
            return 0
        total = 0
        for m_start, m_end in _month_iter(eff_start, eff_end):
            w_start = max(eff_start, m_start)
            w_end = min(eff_end, m_end)
            overlap_days = (w_end - w_start).days
            month_days = _days_in_month(m_start.year, m_start.month)
            total += p.recurring_amount_micros * overlap_days // month_days
        return total

    @staticmethod
    def resolve_revenue_mode(tenant, customer):
        mode = getattr(customer, "revenue_mode", "") or ""
        if mode:
            return mode
        return "metered_only" if tenant.billing_mode == "meter_only" else "billed"

    @staticmethod
    def subscription_nominal_for_window(tenant_id, customer_id, start_date, end_date) -> int:
        from apps.subscriptions.models import StripeSubscription
        subs = StripeSubscription.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id,
            status__in=["active", "trialing", "past_due", "unpaid"])
        total = 0
        for sub in subs:
            per_interval = sub.amount_micros
            monthly = per_interval // 12 if sub.interval == "year" else per_interval
            for m_start, m_end in _month_iter(start_date, end_date):
                w_start = max(start_date, m_start)
                w_end = min(end_date, m_end)
                overlap_days = (w_end - w_start).days
                if overlap_days <= 0:
                    continue
                total += monthly * overlap_days // _days_in_month(m_start.year, m_start.month)
        return total

    @staticmethod
    def accrued_subscription_revenue(tenant_id, customer_id, start_date, end_date) -> int:
        return (RevenueService.manual_revenue_for_window(tenant_id, customer_id, start_date, end_date)
                + RevenueService.subscription_nominal_for_window(tenant_id, customer_id, start_date, end_date))


class SuppliedRevenueService:
    """The two views of a tenant-supplied revenue record, each named (#495).

    Slice 7 §5 is blunt about which of these is the new one: **recognised is
    the only behaviour UBB has today, and it is unlabelled and
    unconditional.** `RevenueService.manual_revenue_for_window` above prorates
    a recurring profile by day every time it is asked, with no way to request
    the figure as recorded and nothing on the wire saying that a division
    happened. So `recorded` is the view that was missing and the labelling is
    the honesty this class adds; the arithmetic is not new.

    **RECORDED places the whole amount on the day the record's period opens.**
    That is the date the tenant stated the figure against, and nothing is
    divided — which is why it is the default every surface falls back to. A
    default that distributes would be the unlabelled proration again, arrived
    at by omission instead of by assumption.

    **RECOGNISED spreads it by the record's own `recognition_method`**, and
    only ever along time. `straight_line` divides by day across the span the
    record itself declares; `on_receipt` lands the whole amount on the opening
    day, so under that method the two views are the same figure — which is
    what the method says, and saying it is the point.

    **The division is integer, by whole days, floor-rounded**, matching the
    arithmetic the accrual helpers above already use so that two revenue
    figures in one response cannot disagree about how a part-month is counted.
    A floor means the recognised parts of a split window can sum to slightly
    less than the supplied amount; that under-states rather than invents, which
    is the direction a revenue figure should err in.
    """

    @staticmethod
    def _span_days(record):
        """Whole days in the record's own declared span, or ``None`` where it
        declared an instant rather than a span."""
        if record.period_end is None:
            return None
        return (record.period_end - record.period_start).days

    @staticmethod
    def _overlap_days(record, start_date, end_date):
        """Whole days of the record's span inside the half-open window."""
        if record.period_end is None:
            return 0
        opens = max(record.period_start, start_date)
        closes = min(record.period_end, end_date)
        return max((closes - opens).days, 0)

    @staticmethod
    def spreads_across_a_span(recognition_method) -> bool:
        """Whether ``recognition_method`` divides an amount across the span the
        record declares — which is the same question as *does this method need
        the record to declare one at all?*

        Public because the write surface asks it before the database does: a
        caller who names a spreading method and omits the period end is told
        which of the two fields to change, rather than meeting an integrity
        error naming a constraint. The check constraint is still the
        enforcement; this is the friendly door in front of it, and both read
        this one map.
        """
        return _SPREADS_ACROSS_THE_SPAN[recognition_method]

    @staticmethod
    def _is_distributed(record, basis):
        """Whether this record is spread across its span at all, under
        ``basis``. The one place the two facts meet, so no caller can consult
        the basis and forget the method or the other way round."""
        return (basis == REVENUE_BASIS_RECOGNISED
                and SuppliedRevenueService.spreads_across_a_span(
                    record.recognition_method))

    @staticmethod
    def contributes(record, start_date, end_date, basis) -> bool:
        """Whether ``record`` has anything to say about the half-open window
        under ``basis``.

        Separate from the amount because a record may legitimately contribute
        **zero** — a tenant recording a free month is stating that revenue was
        nothing, which is a different fact from having supplied nothing at all
        (#153 §3.4) — so a caller that inferred contribution from a zero
        amount would erase exactly the distinction this record exists to make.
        """
        if SuppliedRevenueService._is_distributed(record, basis):
            return SuppliedRevenueService._overlap_days(record, start_date, end_date) > 0
        return start_date <= record.period_start < end_date

    @staticmethod
    def attributed_micros(record, start_date, end_date, basis) -> int:
        """How much of ``record`` the half-open window gets under ``basis``."""
        if not SuppliedRevenueService.contributes(record, start_date, end_date, basis):
            return 0
        if not SuppliedRevenueService._is_distributed(record, basis):
            return record.amount_micros
        span = SuppliedRevenueService._span_days(record)
        overlap = SuppliedRevenueService._overlap_days(record, start_date, end_date)
        # The span is never zero: the record's own check constraint refuses a
        # `straight_line` method without a period end, and refuses an end that
        # does not fall after its start.
        return record.amount_micros * overlap // span

    @staticmethod
    def in_window(tenant_id, customer_id, start_date, end_date, basis):
        """Every supplied record contributing to the window, oldest first.

        The database narrows to records whose span could touch the window at
        all; `contributes` above then settles it per basis, because the two
        bases select different records from that set and expressing both as
        SQL would put the rule in two places.
        """
        from django.db.models import Q
        from apps.subscriptions.economics.models import TenantSuppliedRevenue

        candidates = TenantSuppliedRevenue.objects.filter(
            Q(tenant_id=tenant_id, customer_id=customer_id,
              period_start__lt=end_date),
            Q(period_end__isnull=True) | Q(period_end__gt=start_date),
        ).order_by("period_start", "source_reference")
        return [record for record in candidates
                if SuppliedRevenueService.contributes(record, start_date, end_date, basis)]
