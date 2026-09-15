from django.db import migrations


class Migration(migrations.Migration):
    """Drop the margin snapshot's frozen copy of the revenue switch (#497).

    **THE STATED REASON ADR-0007 §1 REQUIRES.** The snapshot froze, per period,
    the customer-level setting that decided whether that customer's usage
    counted as revenue — a copy of a column `customers/0015_…` drops in this
    same commit. It is dropped rather than carried for two reasons, and the
    second is the one worth writing down.

    **It answered a question that was never about a period.** Every other
    column here is a measurement of one month; this one was a configuration
    value that happened to be read while a month was being closed. A snapshot
    holding a stale copy of a setting is the shape that outlives the setting:
    change the setting and the frozen copies disagree with it forever, with
    nothing raising.

    **And the fact it froze is now per posting.** `Posting.pricing_status`
    (#147 §7) says whether each posting carried customer revenue, and the
    postings of a closed period are still there to be asked. Freezing a coarse
    answer beside a precise one is how the two come to disagree.

    ⚠ **THE COLUMN'S READERS ARE GONE IN THIS COMMIT, NOT LEFT BEHIND.** The
    composition wrote it, the margin schemas published it, and the console read
    it on two surfaces; all four go together, because a contract change the
    console reads and the console's reaction cannot split across commits.

    **No data carried.** The values were derivable from the customer's own
    column, which is itself being dropped; reconstructing them would mean
    reconstructing the rule this ticket exists to delete. `RemoveField` reverses
    in the ordinary Django sense — it re-creates an empty column — and saying
    that plainly is better than claiming irreversibility: what cannot come back
    is the DATA, deliberately, because nothing writes it anywhere first.
    """

    dependencies = [
        ("subscriptions", "0015_the_recurring_amount_becomes_the_periods_it_was_always_about"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customereconomics",
            name="revenue_mode",
        ),
    ]
