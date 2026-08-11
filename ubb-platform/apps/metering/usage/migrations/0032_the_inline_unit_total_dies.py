"""The posting's inline unit total is dropped (#272).

A RETIREMENT, NOT A MOVE, and the distinction is the whole ruling. #270 gave the
posting a child record for what was measured, and this slice had to settle
whether that child carries one column or two. The answer is **one**: the nameless
inline total does not follow the quantities across, it dies.

Under the split it would have acquired a SHORTER LIFE than the billed total
sitting beside it on the same response — the child is prunable and the money is
not — while the read contract's `or 0` coalescing went on rendering its absence
as a currency zero on the end customer's own view. Retiring it deletes that
failure mode instead of instrumenting it.

ADR-0007 §1's third bullet governs this directly — *dropping a column that may
hold rows requires a stated reason in the migration* — and the two paragraphs
above are that reason. The rule beside it, that a column which MOVES carries its
data, does not apply: there is nowhere to carry this one to, which is the ruling
rather than a gap in it. So the reverse below restores the column's SHAPE and
not its contents. Every restored row reads NULL, a value the column always
allowed and which the read contract already coalesced. That is the honest
reverse for a deletion, and it is exercised against a real database in
``tests/test_the_inline_unit_total_dies.py`` rather than asserted to exist.

Nothing reads the column by the time this runs: the same commit clears the model,
metering's read contract, the recording path, both recording routes, six public
schemas, the customer-facing usage summary, the SDK and the console. You cannot
drop a column while a reader survives, and `tests/contracts/
test_the_inline_unit_total_is_gone.py` is what proves none does.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('usage', '0031_the_measurements_become_a_child_record'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='posting',
            name='units',
        ),
    ]
