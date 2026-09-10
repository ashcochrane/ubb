"""The per-owner cap on work already running leaves the risk row — deleted,
not narrowed, not moved (#455, slice 6 §11–§12, #150 §12.5).

**THE COLUMN GOES AND NOTHING CARRIES ITS VALUE (ADR-0007 §1).** The stated
reason: the cap bounded a COUNT of outstanding operations for a billing
owner, which converts to no amount of money — and its existence invited the
belief that UBB closes a blind window it cannot see into (a call already
dispatched to the supplier is spent whatever the count says). Admission
control bounds the RATE of new work, by the column beside this one, and
nothing else. There is no successor column to carry a figure onto, because
there is no successor control: a tenant who configured a cap gets no
refusal for it after this migration, by design, and the work app's
`0025` drops the index that existed only for the cap's count.

Backwards: the column returns with its old default, which is what every
row held before anyone configured it. The figures tenants set are not
restored — there is nothing left to restore them into, and the control
they configured no longer exists to read them.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0011_the_default_ceilings_leave_the_risk_row_for_the_tenant"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="riskconfig",
            name="max_concurrent_requests",
        ),
    ]
