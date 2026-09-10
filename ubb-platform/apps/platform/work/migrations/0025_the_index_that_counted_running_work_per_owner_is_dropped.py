"""The index over (billing owner, status) is dropped with the control that
was its only reader (#455, slice 6 §12, #150 §12.5).

`idx_task_owner_status` existed for one query: the per-owner cap's count of
a billing owner's ACTIVE work at every start. The cap is deleted by
`gating/0012` in the same commit, nothing else scans by that pair (the stop
announcements read the pinned owner off one row, by primary key), and an
index no query uses is one write per insert for nothing. It carries no
data, so backwards simply re-declares it.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0024_a_kind_of_work_declares_its_ceiling_or_declares_itself_uncapped"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="task",
            name="idx_task_owner_status",
        ),
    ]
