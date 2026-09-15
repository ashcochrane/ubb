"""The recurring revenue amount becomes the periods it was always about, and
the model that held it stops existing (#496, slice 7 §9, ADR-0007 §1).

`0014` built `TenantSuppliedRevenue` beside the recurring profile and carried
nothing, because the replacement has to exist before the thing it replaces can
be deleted. This is the other half: **every amount the profile held becomes one
or more per-period records, and then the table goes.**

⚠ **HAND-WRITTEN AND CARRYING ITS DATA, never `makemigrations`' add-plus-remove**
(ADR-0007 §1). An auto-generated pair would drop the table and leave a tenant's
stated revenue history on the floor, which is the one outcome a replacement is
not allowed to have.

**WHAT THE PROFILE ACTUALLY DID, which is what gets carried.** It held one
recurring amount per customer and a span it applied over, and the accrual that
read it walked every CALENDAR MONTH the span touched, adding
`amount x overlap_days // days_in_month` for each. So the amount was never
really a per-customer fact: it was a per-month fact with the months left
implicit, and the profile's own accrual was the only thing that knew it. Each
of those months becomes a record that says so out loud.

⚠ **A PART-PERIOD IS ENTERED AS A PART-PERIOD**, which is the whole reason §9
rules the mid-period affordance into this slice rather than treating it as a
loss. A profile that began on the fourteenth becomes a record from the
fourteenth to the month end carrying that stretch's share — the span DECLARED
where the retired model could only ever express it by dividing, invisibly, on
every read.

⚠ **THE LABEL AND THE ARITHMETIC DISAGREED, AND THE CARRY FOLLOWS THE
ARITHMETIC.** The profile carried an `interval` of `month` or `year`, and
**nothing ever divided by it**: the accrual multiplied the amount into every
calendar month whatever the interval said, while the Stripe accrual one
function below it did divide a yearly amount by twelve. So a yearly profile of
X was accruing X per month, and a tenant reading its margin was reading that.
Restating that history to match a label nothing read would be this migration
inventing a number rather than moving one, so the interval is dropped and the
months are what survive. `apps/subscriptions/tests/` holds the equality.

**THE HORIZON, and why an open-ended profile has one.** A profile with no
`effective_to` asserted revenue forever — every future window it was asked
about produced an amount. A per-period record asserts a period, and there is no
honest number of future periods to write. So an open profile is carried through
the month this migration RUNS in and no further: everything it actually
produced becomes a record, and the next period becomes a record when the tenant
states it, which is the write surface `0014` landed. **This is the one place
the replacement is narrower than what it replaces, and narrowing a claim about
the future to a claim about the past is the direction to be wrong in.**

**WHAT EACH CARRIED ROW SAYS:**

* `period_start` / `period_end` — the month, or the part of it the span
  covered, half-open like every other span on this record;
* `amount_micros` — that month's share, by the accrual's own arithmetic. ⚠ That
  is only HALF of "a window's total is the same figure before and after": the
  other half is that margin reads these rows on the `recognised` basis
  (`MARGIN_REVENUE_BASIS`), so a window covering part of a row's span gets that
  part. Read on the `recorded` basis instead, a month-to-date window would get
  a whole month's revenue against a few days' cost;
* `recognition_method` — `straight_line`, which is what the accrual was doing
  unlabelled: dividing an amount evenly across a span by day. Labelling it is
  the point of the record it lands on;
* `currency` — the profile's own;
* `source_reference` — **UBB's own handle, because the tenant never had one to
  give.** The record refuses a blank one and is right to: a figure whose source
  is unstated is the thing being replaced. What is honest here is to say where
  the number came from, which is this migration, and a tenant looking at a row
  bearing it knows it predates the record and was never typed by anyone.

**A ZERO AMOUNT CARRIES NOTHING.** The accrual's own first line returned zero
for a profile holding zero without ever looking at its span, so the profile was
saying "nothing is configured" rather than "nothing was earned". Those are
different facts (#153 §3.4) and a zero-amount record would turn the first into
the second.

**THE REVERSE IS PROVIDED AND IS LOSSY IN ONE NAMED PLACE.** It deletes the
rows this migration wrote — identified by the source reference above, so a
figure a tenant supplied itself is never touched — and rebuilds one profile per
customer from them: the amount is a whole month's, the span runs from the
earliest period open to the latest period close. What does not come back is
**whether the profile was open-ended**, because the horizon closed it and
nothing in the rows records which end was the profile's own. Everything else
round-trips. Nothing is deployed; the rows this touches exist on developer
machines and in fixtures only.
"""
import calendar

from django.db import migrations, models
from django.utils import timezone

#: A second encoding of a name the registry declares, necessarily so: a
#: migration must not import application code. `apps/subscriptions/tests/` holds
#: it to `core.vocabulary`'s constant.
RECOGNITION_METHOD = "straight_line"

#: THE HANDLE A CARRIED ROW CARRIES. Not a tenant's invoice number, because
#: there never was one — the retired model had no source field at all, which is
#: one of the four structural reasons #153 §3.3 ruled it replaced rather than
#: widened. It names this migration so that the provenance of a carried figure
#: is exactly as readable as the provenance of a supplied one, which is the
#: whole point of the column it goes in.
SOURCE_REFERENCE = "ubb:carried-from-the-retired-recurring-amount"


def _month_after(day):
    """The first of the month following `day`'s."""
    return (day.replace(year=day.year + 1, month=1, day=1)
            if day.month == 12 else day.replace(month=day.month + 1, day=1))


def the_horizon(today):
    """The first day of the month after `today`'s — the close an open-ended
    profile is carried up to, so the month the migration runs in is carried
    whole and no month after it is claimed at all."""
    return _month_after(today)


def carried_rows(profile, horizon):
    """Every per-period record one profile becomes, oldest first.

    Pure: it reads FOUR of the retired model's fields and returns dictionaries.
    Four rather than five is the point — `interval` is the one it does not
    read, because the accrual did not read it either, and the case that holds
    that is `TestTheLabelAndTheArithmeticDisagreed`.

    The arithmetic is the retired accrual's own, month by month. That is what
    makes a window's revenue the same figure before and after, and the other
    half of that guarantee is on the reading side: `MARGIN_REVENUE_BASIS`
    serves these rows on the `recognised` basis, so a window that covers part
    of a row's span gets that part — which is the day-proration the accrual
    performed. Both halves are pinned in `apps/subscriptions/tests/`.
    """
    if not profile.recurring_amount_micros:
        return []
    opens = profile.effective_from
    closes = horizon if profile.effective_to is None else min(
        profile.effective_to, horizon)
    if closes <= opens:
        return []

    rows, month = [], opens.replace(day=1)
    while month < closes:
        next_month = _month_after(month)
        period_start = max(opens, month)
        period_end = min(closes, next_month)
        overlap_days = (period_end - period_start).days
        days_in_month = calendar.monthrange(month.year, month.month)[1]
        rows.append({
            "period_start": period_start,
            "period_end": period_end,
            "amount_micros": (profile.recurring_amount_micros
                              * overlap_days // days_in_month),
            "currency": profile.currency,
            "recognition_method": RECOGNITION_METHOD,
            "source_reference": SOURCE_REFERENCE,
        })
        month = next_month
    return rows


def carry_the_amounts_onto_their_periods(apps, schema_editor, horizon=None):
    """Every profile becomes its months, on the record that replaced it.

    `horizon` is an argument so the month this runs in is the caller's to
    state: the migration passes today's, and the cases that hold the arithmetic
    pass a fixed one rather than a date that moves under them.
    """
    Profile = apps.get_model("subscriptions", "CustomerRevenueProfile")
    Supplied = apps.get_model("subscriptions", "TenantSuppliedRevenue")
    horizon = horizon or the_horizon(timezone.now().date())

    for profile in Profile.objects.all().iterator():
        for row in carried_rows(profile, horizon):
            # Re-stating rather than inserting, because the record's own
            # uniqueness key says a figure for one customer, one period open
            # and one source is one figure. A migration that is run again after
            # failing part-way through then states the same figures rather than
            # doubling a tenant's revenue.
            Supplied.objects.update_or_create(
                tenant_id=profile.tenant_id, customer_id=profile.customer_id,
                period_start=row["period_start"],
                source_reference=row["source_reference"],
                defaults={"amount_micros": row["amount_micros"],
                          "currency": row["currency"],
                          "period_end": row["period_end"],
                          "recognition_method": row["recognition_method"]})


def put_the_amounts_back(apps, schema_editor):
    """One profile per customer, rebuilt from the rows the forward wrote.

    Only from those rows: the source reference is what separates a carried
    figure from one a tenant supplied itself, and a reverse that swept up the
    second would delete a fact this migration never created.
    """
    Profile = apps.get_model("subscriptions", "CustomerRevenueProfile")
    Supplied = apps.get_model("subscriptions", "TenantSuppliedRevenue")

    carried = Supplied.objects.filter(source_reference=SOURCE_REFERENCE)
    by_customer = {}
    for record in carried.order_by("period_start").iterator():
        key = (record.tenant_id, record.customer_id)
        by_customer.setdefault(key, []).append(record)

    for (tenant_id, customer_id), records in by_customer.items():
        # A WHOLE month's amount, not a part-month's: the forward divided the
        # first and last months by day where the span began or ended inside
        # them, so a part row is a fraction of the recurring amount and only a
        # whole row is the amount itself. Where every row is a part row — a
        # profile that lived inside one month — the largest is the closest
        # statement of it there is.
        whole = max(
            records,
            key=lambda record: (record.period_end - record.period_start).days)
        days = (whole.period_end - whole.period_start).days
        days_in_month = calendar.monthrange(
            whole.period_start.year, whole.period_start.month)[1]
        Profile.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id,
            defaults={
                "recurring_amount_micros": (
                    whole.amount_micros * days_in_month // days),
                "interval": "month",
                "currency": whole.currency,
                "effective_from": records[0].period_start,
                "effective_to": records[-1].period_end,
            })
    carried.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0014_a_tenant_may_state_what_it_earned_elsewhere"),
    ]

    operations = [
        # THE COLUMN THAT ENDS THE PROVENANCE DESTRUCTION. The snapshot's
        # `subscription_revenue_micros` held manual and Stripe revenue added
        # together — its own comment said `manual + stripe` — so a reader of
        # the number could not say which kind of money it was. Two sources,
        # two columns, and then no surface has to be trusted to remember.
        migrations.AddField(
            model_name="customereconomics",
            name="supplied_revenue_micros",
            field=models.BigIntegerField(default=0),
        ),
        # THE CARRY RUNS WHILE BOTH MODELS STILL EXIST, which is the only
        # window in which it can.
        migrations.RunPython(
            carry_the_amounts_onto_their_periods, put_the_amounts_back),
        migrations.RemoveConstraint(
            model_name="customerrevenueprofile",
            name="uq_revenue_profile_tenant_customer",
        ),
        migrations.DeleteModel(name="CustomerRevenueProfile"),
    ]
