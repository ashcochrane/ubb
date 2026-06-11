import calendar


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
