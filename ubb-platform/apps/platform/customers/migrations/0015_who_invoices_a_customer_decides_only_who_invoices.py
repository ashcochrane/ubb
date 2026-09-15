from django.db import migrations


class Migration(migrations.Migration):
    """Drop the customer-level revenue switch (#497, slice 7 §9).

    **THE STATED REASON ADR-0007 §1 REQUIRES FOR DROPPING A COLUMN THAT MAY
    HOLD ROWS.** The column carried a per-customer override of whether that
    customer's metered usage counted as revenue at all, blank meaning *derive
    it from the tenant's billing mode*. It is dropped rather than carried, and
    the argument is that there is nothing to carry: every value it could hold
    was an answer to a question it had no business answering.

    **Who raises a customer's invoices is not who earned the money.** The
    column let "UBB does not bill this customer" become "this customer
    produced no revenue" — the inversion #141 §1.1's governing invariant
    forbids — and the question it was standing in for has been answered
    precisely, per posting, since #147 §7: `Posting.pricing_status` says
    whether a price is `known`, `waived`, `unknown` or `not_applicable`, and
    `not_applicable_reason` says which of the two causes applies when it does
    not. Four facts per posting, each written by the code that knows it,
    against one coarse setting per customer that guessed.

    ⚠ **A PUBLISHED NUMBER MOVES FOR SOME TENANTS, AND THAT IS THE POINT OF
    THE TICKET RATHER THAN A SIDE EFFECT.** A customer this column resolved
    away from billed usage reported `usage_revenue_micros` as zero and a
    margin equal to the negative of its cost; from this migration on it
    reports the billed total its own postings carry. The figure was wrong
    before and is right after — UBB resolved those prices, and it resolved
    them *because the tenant's own margin reporting is what they are resolved
    for* (`apps/metering/pricing/applicability.py`). A tenant that has
    declared no prices is unaffected: its postings resolve `unknown`, sum to
    nothing, and travel with `unpriced_event_count` saying the total is a
    floor — which is the honest "revenue unknown", arrived at from the
    postings rather than from a billing mode.

    **No data migration.** There is no destination column: the replacement is
    not a different place to store the answer, it is that the answer is
    already stored somewhere better, per posting, and was before this column
    existed. `apps/subscriptions/migrations/0016_…` drops the frozen copy of
    the same setting from the margin snapshot, for the same reason and in the
    same commit.

    ⚠ **AND IT DECLARES NO EDGE TO THAT ONE, DELIBERATELY.** An earlier draft
    made this migration depend on it, reasoning that the pair should not apply
    half-way. A dependency cannot buy that — it picks an ORDER, and a
    half-applied state exists under either order — and the two operations are
    independent anyway: different tables, no foreign key between the columns,
    neither reading the other. What the edge would really have bought is a
    migration in the platform KERNEL depending on a product app, which is the
    wrong direction for ADR-001 and which nothing checks, because
    `test_product_boundaries.py` reads imports rather than migration graphs.

    `RemoveField` is reversible in the ordinary Django sense — reversing it
    re-creates an empty column — and that is worth saying plainly rather than
    claiming irreversibility: what cannot be recovered is the DATA, because
    nothing here writes it anywhere first. That is the intent.
    """

    dependencies = [
        ("customers", "0014_customer_suspension_reason"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customer",
            name="revenue_mode",
        ),
    ]
