# Upward live-balance repair audit trail (#45, delivery spec §D) + the three
# repair outcomes joining the PatrolOutcome vocabulary.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gating', '0008_patroloutcome'),
        ('customers', '0014_customer_suspension_reason'),
        ('tenants', '0019_two_position_enforcement_mode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patroloutcome',
            name='outcome',
            field=models.CharField(choices=[('reminted', 'Re-minted announcement'), ('flag_realigned', 'Stop flag re-aligned'), ('sweep_killed', 'Task swept into the kill flow'), ('repaired', 'Live balance repaired upward'), ('repaired_micros', 'Micros applied by upward repairs'), ('repair_lapsed', 'Repair candidate lapsed')], max_length=20),
        ),
        migrations.CreateModel(
            name='LiveBalanceRepair',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('candidate', 'Candidate'), ('repaired', 'Repaired'), ('lapsed', 'Lapsed')], default='candidate', max_length=10)),
                ('first_deficit_micros', models.BigIntegerField()),
                ('second_deficit_micros', models.BigIntegerField(blank=True, null=True)),
                ('applied_micros', models.BigIntegerField(blank=True, null=True)),
                ('live_before_micros', models.BigIntegerField(blank=True, null=True)),
                ('live_after_micros', models.BigIntegerField(blank=True, null=True)),
                ('durable_balance_micros', models.BigIntegerField()),
                ('pending_hold_micros', models.BigIntegerField()),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_balance_repairs', to='customers.customer')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_balance_repairs', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_live_balance_repair',
                'constraints': [models.UniqueConstraint(condition=models.Q(('status', 'candidate')), fields=('owner',), name='uq_live_balance_repair_open_candidate')],
            },
        ),
    ]
