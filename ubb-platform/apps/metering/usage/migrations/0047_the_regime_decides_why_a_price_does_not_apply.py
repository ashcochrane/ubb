"""The pricing regime decides why a price does not apply, for every tenant
(#553, the owner's C2 ruling of 2026-10-08, ADR-0021 §5).

A fixed-price unit's event postings carry `not_applicable` with the reason
`fixed_task_pricing` for every tenant now; `tenant_not_billing` — the posture
value, "posture wins" (#418) — lost its only producer
(`pricing/applicability.py`) in the same change, and a value nothing can
produce is deleted with its last producer rather than kept alive. Two
operations, and the first needs its argument written down.

1. **The postings that hold it are rewritten.** Every one of them is a
   metering-only tenant's fixed-price event posting — the old producer was the
   fixed-price branch and nothing else — and the reason that was always true of
   them is `fixed_task_pricing`: the revenue for the event sits on its unit's
   Charge. UBB is pre-live and not deployed (ADR-0007 §5), so the rows this
   reaches are a developer's or a test's.

   ⚠ **THE DATABASE REFUSES THIS UPDATE AS WRITTEN, ON PURPOSE.** The posting's
   price trigger (`trg_posting_price_transitions`, `0039`, widened by `0046`)
   admits exactly one change to `not_applicable_reason` — none, beside the one
   resolution `unknown` to `known` — and that is its stated purpose: a
   resolved reason is not re-diagnosed in place, from a route, a shell or a
   migration alike. So the rewrite LIFTS EXACTLY THAT TRIGGER FOR EXACTLY THIS
   ONE UPDATE, inside this migration's one transaction: `DISABLE TRIGGER` on
   that trigger by name, the `UPDATE` naming the one value it rewrites, and
   `ENABLE TRIGGER` before the transaction ends. Postgres runs all three as
   transactional DDL, so there is no state in which the trigger is disabled
   and anything else can write: a failure anywhere rolls the lift back with
   the rows. The function is not replaced and not weakened.
   `apps/metering/usage/tests/test_the_regime_decides_why_a_price_does_not_apply.py`
   pins that, once this has run, the trigger is ENABLED (`pg_trigger.tgenabled`)
   and still refuses a reason rewrite through every door. ADR-0021 records it
   as a one-time pre-live exception to resolve-once, which is what it is.

   **What is not rewritten:** a sealed Pricing Receipt is RESOLVE_ONCE and
   keeps `tenant_not_billing` in its `pricing.detail` as written. No reader
   validates that detail against the live value set (`receipts.validate_receipt`
   checks the record's shape, and the receipt is published as an untyped
   object), so it reads as the history it is.

2. **The closed set loses the member**, at the column's choices and at
   `ck_posting_not_applicable_reason`, dropped and re-added because a `CHECK`
   has no `ALTER`. After step 1 no row can fail it. The combination check
   `ck_posting_pricing_status_agrees_with_the_price` names no member — its
   `not_applicable` arm asks only that a reason is present — so it is left as
   `0046` wrote it, `pricing_status_reason` terms and all.

**The reverse** re-admits the member at the choices and the check. It does not
put the old value back on any row: which rows held it is not recoverable, and
`fixed_task_pricing` stays true of every one of them.

**The literals are frozen**, for the reason `0036` gives: a migration records
the schema as it was on the day it ran.
"""

from django.db import migrations, models

TRIGGER = "trg_posting_price_transitions"
REMOVED = "tenant_not_billing"
THE_REASON_THAT_WAS_ALWAYS_TRUE = "fixed_task_pricing"

#: The one statement the trigger is lifted for, between the lift and its
#: return — all three inside the migration's transaction.
REWRITE = f"""
ALTER TABLE ubb_posting DISABLE TRIGGER {TRIGGER};
UPDATE ubb_posting
   SET not_applicable_reason = '{THE_REASON_THAT_WAS_ALWAYS_TRUE}'
 WHERE not_applicable_reason = '{REMOVED}';
ALTER TABLE ubb_posting ENABLE TRIGGER {TRIGGER};
"""


def rewrite_the_postings_that_hold_it(apps, schema_editor):
    schema_editor.execute(REWRITE, params=None)


class Migration(migrations.Migration):

    # The lift, the rewrite and the return are one transaction (the default
    # for a Postgres migration, stated so nobody turns it off): there is no
    # committed moment at which the trigger is disabled.
    atomic = True

    dependencies = [
        ("usage", "0046_the_price_status_carries_its_own_reason"),
    ]

    operations = [
        # 1. The rows, under the one-time lift.
        migrations.RunPython(rewrite_the_postings_that_hold_it,
                             migrations.RunPython.noop),
        # 2. The closed set, at the column and at the database.
        migrations.AlterField(
            model_name="posting",
            name="not_applicable_reason",
            field=models.CharField(
                blank=True, max_length=32, null=True,
                choices=[("fixed_task_pricing", "fixed_task_pricing")]),
        ),
        migrations.RemoveConstraint(
            model_name="posting",
            name="ck_posting_not_applicable_reason",
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("not_applicable_reason__isnull", True),
                    ("not_applicable_reason__in", ["fixed_task_pricing"]),
                    _connector="OR",
                ),
                name="ck_posting_not_applicable_reason",
            ),
        ),
    ]
