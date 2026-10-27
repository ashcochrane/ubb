"""How a Stripe amount becomes a mirrored one — kept as Stripe stated it, and
admitted into UBB's economics only in UBB's one currency (#564, ADR-0023 §7).

Every writer of the two mirror tables reads through here: the subscription
webhooks, the poll sync, the orchestrator, the invoice webhook and its poller
repair. Before this module each of them scaled Stripe's integer by the TENANT's
minor unit and called the result an amount, which put a connected account's
euros into revenue as dollars. Now the integer is kept exactly as Stripe sent it
beside the currency Stripe named, and the economic amount exists only where the
one policy admits that currency. A foreign fact is QUARANTINED: kept, never
converted, never relabelled, and left out of every aggregate, each of which
says how many it left out.
"""
import logging
from collections import namedtuple
from datetime import datetime, timezone as dt_timezone

from core.currency_policy import ECONOMIC_CURRENCY, is_admitted
from core.money import from_minor

logger = logging.getLogger(__name__)

#: A mirrored subscription's money, as the five columns its writers set.
MirroredAmount = namedtuple(
    "MirroredAmount",
    "currency source_amount_minor amount_micros seat_qty interval")


def source_currency(code):
    """The currency Stripe named, in its canonical spelling — case and padding
    are spelling, not a second currency — or ``""`` where it named none.

    Never a default: an amount whose currency the source did not state is not
    an amount in US dollars, and calling it one is the relabel #564 forbids.
    """
    return code.strip().lower() if isinstance(code, str) else ""


def economic_micros(currency, source_amount_minor):
    """Micros of UBB's one currency for a source amount — exact — or ``None``
    where the one policy does not admit the source's currency: there is no FX,
    so no amount in US dollars exists to state."""
    if not is_admitted(currency):
        return None
    return from_minor(source_amount_minor, ECONOMIC_CURRENCY)


def mirrored_amounts(stripe_sub):
    """A Stripe subscription's money, mirrored.

    ``source_amount_minor`` is Σ licensed ``unit_amount × quantity`` across
    access and seat, the integers Stripe sent in the subscription's own minor
    unit; metered items contribute nothing (their revenue arrives as invoice
    items). ``amount_micros`` is that sum in UBB's one currency, or ``None``.
    """
    currency = source_currency(stripe_sub.get("currency"))
    total, seat_qty, interval = 0, 1, "month"
    for it in stripe_sub["items"]["data"]:
        price = it["price"]; rec = price.get("recurring") or {}
        interval = rec.get("interval", interval)
        if rec.get("usage_type") == "metered":
            continue
        qty = it.get("quantity", 1) or 1
        total += (price.get("unit_amount") or 0) * qty
        if qty > 1:
            seat_qty = qty
    return MirroredAmount(currency, total, economic_micros(currency, total),
                          seat_qty, interval)


def paid_amounts(invoice):
    """``(currency, source_amount_paid_minor, amount_paid_micros)`` for a
    Stripe invoice: what it says was paid, kept exactly, and admitted only in
    UBB's one currency. The webhook and its poller repair both read this, so
    the two can never state one invoice two ways."""
    currency = source_currency(getattr(invoice, "currency", None))
    paid = getattr(invoice, "amount_paid", 0) or 0
    return currency, paid, economic_micros(currency, paid)


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
