"""Shared setup for the tests of revenue a tenant collects somewhere UBB
cannot see (`docs/conventions/testing.md` — shared setup helpers live beside
the tests that use them, and are reused rather than re-scaffolded by hand).

ONE FIXTURE, TWO MODULES, TWO SEAMS. The supplied revenue record is proved at
both ends: `apps/subscriptions/tests/test_tenant_supplied_revenue.py` drives
its rule and its four checks at the DATABASE, and
`api/v1/tests/test_a_tenant_may_supply_the_revenue_ubb_cannot_see.py` drives
the ROUTE. What they share is the tenant the record only makes sense for and
the period both describe; what they do with it — an ORM write and a raw
`INSERT` on one side, an authenticated `POST` and `GET` on the other — stays
each module's own, because those are the seams and not the setup.
"""
from datetime import date

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import RECOGNITION_METHOD_STRAIGHT_LINE

#: A WHOLE CALENDAR MONTH, half-open. Thirty days, so a straight-line division
#: has a round number to divide by and an assertion about part of the month is
#: arithmetic a reader can do in their head.
MONTH_OPENS = date(2026, 4, 1)
MONTH_CLOSES = date(2026, 5, 1)

#: THIRTY DAYS AT 100,000 MICROS A DAY. The relationship between this and the
#: span above is what makes the route module's recognised figures readable;
#: the database module needs only a valid amount and inherits it so the two
#: cannot come to describe different records.
SUPPLIED = 3_000_000

#: The tenant's own handle for where the figure came from — an invoice number
#: out of a billing system UBB has never seen, which is exactly what
#: `source_reference` is for.
ITS_OWN_INVOICE = "INV-2026-04-0117"


def a_tenant_billing_its_customers_elsewhere(name="Bills elsewhere",
                                             external_id="c1"):
    """A tenant UBB meters for and never bills, and one of its customers.

    ⚠ **THE BILLING MODE IS LEFT AT ITS DEFAULT AND THAT IS THE POINT.** The
    platform default IS this posture, so naming it would add nothing — and it
    would spell the value the registry has already retired, which the
    forbidden-term sweep refuses in any file that does not already carry it.

    This is the posture the supplied revenue record exists for, and the one
    #495 warns is easiest to build badly: a path built only for tenants UBB
    invoices is the failure no gate here can catch.
    """
    tenant = Tenant.objects.create(name=name, products=["metering"])
    customer = Customer.objects.create(tenant=tenant, external_id=external_id)
    return tenant, customer


def a_tenant_ubb_invoices(name="Invoiced by UBB", external_id="c1"):
    """The mirror: a tenant whose customers UBB bills, and one of its customers.

    ⚠ **IT LIVES HERE BECAUSE THE PAIR IS THE POINT** (#497). The helper above
    describes the posture that is easy to build badly; this one describes the
    ordinary posture, and the assertion that matters is that the two get the
    SAME answer from the same facts. A fixture for either one alone cannot make
    that comparison, so a module holding only one of them is a module that has
    to re-scaffold the other by hand — which is exactly what
    `docs/conventions/testing.md` puts shared setup here to stop.
    """
    tenant = Tenant.objects.create(
        name=name, products=["metering", "billing"], billing_mode="postpaid")
    customer = Customer.objects.create(tenant=tenant, external_id=external_id)
    return tenant, customer


def a_supplied_figure(**stated):
    """The fields of one supplied revenue record, with this fixture's defaults.

    ONE SET OF DEFAULTS FOR THREE WRITERS — the ORM door, the raw-SQL door and
    the route — each of which overrides whichever field its case is about. Three
    copies of a six-field default block is three places for the fixture's April
    to stop being one April.

    Returned as DATES rather than ISO strings: the two database doors want date
    objects and the route wants text, and one `isoformat()` at the caller that
    needs it is cheaper than a second builder here.
    """
    stated.setdefault("amount_micros", SUPPLIED)
    stated.setdefault("currency", "usd")
    stated.setdefault("period_start", MONTH_OPENS)
    stated.setdefault("period_end", MONTH_CLOSES)
    stated.setdefault("recognition_method", RECOGNITION_METHOD_STRAIGHT_LINE)
    stated.setdefault("source_reference", ITS_OWN_INVOICE)
    return stated


def a_mirrored_subscription(**fields):
    """A mirrored Stripe subscription, written as `mirrored_amounts` writes one.

    THE SOURCE INTEGER IS STATED, NEVER DEFAULTED (#564). A mirror row keeps
    what Stripe sent beside the dollar amount UBB derives from it, and a column
    default would be a source figure nobody sent. So a fixture names the amount
    it means and this states the integer Stripe sends for it: for a US-dollar
    subscription, that amount in cents, exactly. A fixture whose subject is a
    FOREIGN subscription states its own — `currency`, `source_amount_minor` and
    `amount_micros=None` — and this leaves them alone.
    """
    from apps.subscriptions.models import StripeSubscription
    from core.money import to_minor

    if "source_amount_minor" not in fields:
        minor, remainder = to_minor(fields["amount_micros"],
                                    fields.get("currency", "usd"))
        assert not remainder, "a dollar fixture is a whole number of cents"
        fields["source_amount_minor"] = minor
    return StripeSubscription.objects.create(**fields)


SK = "sk_test_sentinel"


def a_licensed_item(unit_amount, qty=1, *, interval="month", product_name=None,
                    item_id=None, price_id=None, period_start=1738368000,
                    period_end=1740960000, usage_type="licensed"):
    """One subscription item, as Stripe's JSON states it. `product_name` set
    means the price's product was EXPANDED (a Product object); unset, Stripe
    sends the product as an id string, which has no name."""
    price = {"id": price_id or f"price_{unit_amount}", "object": "price",
             "unit_amount": unit_amount,
             "recurring": {"interval": interval, "usage_type": usage_type},
             "product": ({"id": "prod_1", "object": "product", "name": product_name}
                         if product_name is not None else "prod_1")}
    return {"id": item_id or f"si_{unit_amount}_{qty}", "object": "subscription_item",
            "price": price, "quantity": qty,
            "current_period_start": period_start, "current_period_end": period_end}


def a_subscription_dict(id, customer, status, *, items, currency="usd", **extra):
    """The JSON of a Basil-shaped Stripe Subscription (items.data[])."""
    data = {"id": id, "object": "subscription", "customer": customer, "status": status,
            "currency": currency, "items": {"object": "list", "data": list(items),
                                            "has_more": False,
                                            "url": f"/v1/subscription_items?subscription={id}"}}
    data.update(extra)
    return data


def a_stripe_subscription(id, customer, status, *, items, currency="usd", **extra):
    """A GENUINE ``stripe.Subscription`` (Stage C1a, F-3b): what the pinned
    stripe-python 15.2.0 delivers from a webhook, a list or a create — a
    StripeObject with no ``.get``, whose ``items.data[]`` are
    ``SubscriptionItem``s, whose ``price.recurring`` and an expanded
    ``price.product`` are StripeObjects too. Replaces the dict-subclass fake
    that kept the ``.get`` code green."""
    import stripe
    return stripe.Subscription.construct_from(
        a_subscription_dict(id, customer, status, items=items, currency=currency, **extra), SK)


def a_subscription_event(event_id, kind, sub_dict, *, account=None, livemode=True):
    """A GENUINE ``stripe.Event`` whose ``data.object`` is a real
    ``stripe.Subscription`` — the object ``Webhook.construct_event`` hands a
    handler. ``account`` is absent when None."""
    import stripe
    import time
    data = {"id": event_id, "object": "event", "type": kind, "livemode": livemode,
            "created": int(time.time()), "data": {"object": sub_dict}}
    if account is not None:
        data["account"] = account
    return stripe.Event.construct_from(data, SK)
