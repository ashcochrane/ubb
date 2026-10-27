"""A Stripe amount is kept as Stripe sent it, and admitted only in US dollars (#564).

Until this migration every writer of the two mirror tables scaled Stripe's
integer by the TENANT's minor unit and stored the result as an amount, beside
the currency Stripe named — so a connected account's euros reached revenue and
margin as dollars. Now each row keeps:

  * `currency` — what Stripe named, the SOURCE fact, whatever it is;
  * `source_amount_minor` / `source_amount_paid_minor` — Stripe's own integer,
    exactly as sent, in that currency's minor unit (never micros: ADR-0006 §1);
  * `amount_micros` / `amount_paid_micros` — the ECONOMIC amount in micros of
    UBB's one currency, NULL wherever the source currency is not US dollars.
    There is no FX, so a foreign subscription has no dollar amount to state; it
    is QUARANTINED — kept, excluded from every aggregate, and counted.

A `CHECK` on each table holds the pairing (an economic amount exactly when the
source currency is US dollars), so no row can carry a relabelled amount. It
does not hold `currency` itself: the foreign code is the evidence (ADR-0023).

**The data step recovers Stripe's integer exactly, and refuses rather than
rounds.** Every amount stored before this migration was Stripe's integer times
the minor unit of the tenant's currency, and `core.money` represented only
two-decimal currencies, so that multiplier was 10,000 for every row: dividing
by it gives back what Stripe sent. A stored amount that is not a whole number
of minor units was not written by any of those writers; the step names it and
stops rather than inventing a source figure. Then a foreign row's economic
amount — the relabel — is cleared. Nothing is deployed, so on every real
database this moves nothing.

`CustomerEconomics.foreign_currency_subscription_count` joins the alerting
snapshot's two counts: what the frozen subscription revenue left out.

**The reverse puts back the shape that was** — the scaled amount on every row
— and drops what this added.
"""

from django.db import migrations, models

#: The multiplier every pre-#564 writer applied: the minor unit of a two-decimal
#: currency, the only kind `core.money` represented. Spelled here rather than
#: read from `core.money`, because it is a fact about the rows this migration
#: found, not about what UBB represents later.
TWO_DECIMAL_MICROS_PER_MINOR_UNIT = 10_000

#: UBB's one currency, spelled as the rows spell it.
USD = "usd"

#: ``(model, economic amount column, source amount column)``.
MIRRORED = (
    ("StripeSubscription", "amount_micros", "source_amount_minor"),
    ("SubscriptionInvoice", "amount_paid_micros", "source_amount_paid_minor"),
)


def state_the_source_amounts(apps, schema_editor):
    for model_name, amount, source in MIRRORED:
        model = apps.get_model("subscriptions", model_name)
        for row in model.objects.all().only("id", "currency", amount):
            stored = getattr(row, amount)
            minor, rest = divmod(stored, TWO_DECIMAL_MICROS_PER_MINOR_UNIT)
            if rest:
                raise RuntimeError(
                    f"{model._meta.db_table} row {row.pk} stores {amount}="
                    f"{stored}, which is not a whole number of minor units, so "
                    f"no Stripe integer produced it. This migration recovers "
                    f"Stripe's figure by dividing and will not round one into "
                    f"being; correct the row, then migrate again.")
            model.objects.filter(pk=row.pk).update(**{
                source: minor,
                amount: stored if row.currency == USD else None})


def put_the_scaled_amounts_back(apps, schema_editor):
    for model_name, amount, source in MIRRORED:
        model = apps.get_model("subscriptions", model_name)
        for row in model.objects.all().only("id", source):
            model.objects.filter(pk=row.pk).update(**{
                amount: getattr(row, source) * TWO_DECIMAL_MICROS_PER_MINOR_UNIT})


def _pairing(amount, name):
    return models.CheckConstraint(
        condition=(models.Q(currency=USD, **{f"{amount}__isnull": False})
                   | (~models.Q(currency=USD)
                      & models.Q(**{f"{amount}__isnull": True}))),
        name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0017_supplied_revenue_is_usd_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="stripesubscription",
            name="source_amount_minor",
            field=models.BigIntegerField(null=True)),
        migrations.AddField(
            model_name="subscriptioninvoice",
            name="source_amount_paid_minor",
            field=models.BigIntegerField(default=0)),
        migrations.AlterField(
            model_name="stripesubscription",
            name="amount_micros",
            field=models.BigIntegerField(null=True)),
        migrations.AlterField(
            model_name="subscriptioninvoice",
            name="amount_paid_micros",
            field=models.BigIntegerField(default=0, null=True)),
        migrations.RunPython(state_the_source_amounts,
                             put_the_scaled_amounts_back),
        migrations.AlterField(
            model_name="stripesubscription",
            name="source_amount_minor",
            field=models.BigIntegerField()),
        migrations.AddConstraint(
            model_name="stripesubscription",
            constraint=_pairing(
                "amount_micros", "ck_subscription_economic_amount_only_in_usd")),
        migrations.AddConstraint(
            model_name="subscriptioninvoice",
            constraint=_pairing(
                "amount_paid_micros",
                "ck_subscription_invoice_economic_amount_only_in_usd")),
        migrations.AddField(
            model_name="customereconomics",
            name="foreign_currency_subscription_count",
            field=models.IntegerField(default=0)),
    ]
