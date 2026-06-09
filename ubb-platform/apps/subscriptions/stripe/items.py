import logging
from datetime import datetime, timezone as dt_timezone

logger = logging.getLogger(__name__)


def _sum_items(stripe_sub):
    """(amount_micros, seat_qty, interval). amount = Sum(licensed unit_amount*qty) across access+seat;
    metered items contribute 0 (their revenue arrives as InvoiceItems)."""
    total, seat_qty, interval = 0, 1, "month"
    for it in stripe_sub["items"]["data"]:
        price = it["price"]; rec = price.get("recurring") or {}
        interval = rec.get("interval", interval)
        if rec.get("usage_type") == "metered":
            continue
        qty = it.get("quantity", 1) or 1
        total += (price.get("unit_amount") or 0) * 10_000 * qty
        if qty > 1:
            seat_qty = qty
    return total, seat_qty, interval


def _u(ts):
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc) if ts else None


def _period_start(stripe_sub):
    s = [i.get("current_period_start") for i in stripe_sub["items"]["data"] if i.get("current_period_start")]
    return _u(s[0]) if s else None


def _period_end(stripe_sub):
    e = [i.get("current_period_end") for i in stripe_sub["items"]["data"] if i.get("current_period_end")]
    if len(set(e)) > 1:
        logger.warning("subscription has mixed item billing periods")
    return _u(e[0]) if e else None


def _product_name(stripe_sub):
    for it in stripe_sub["items"]["data"]:
        prod = (it["price"] or {}).get("product")
        if isinstance(prod, dict) and prod.get("name"):
            return prod["name"]
    return ""
