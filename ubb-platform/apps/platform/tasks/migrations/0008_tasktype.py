import apps.platform.tasks.models
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_task_idx_task_active_limited'),
        ('tenants', '0022_tenantapikey_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.SlugField(max_length=64)),
                ('kind', models.CharField(choices=[('task', 'Task'), ('subtask', 'Subtask')], default='task', max_length=8)),
                ('default_provider_cost_limit_micros', models.BigIntegerField(blank=True, null=True)),
                ('required_dimensions', models.JSONField(blank=True, default=apps.platform.tasks.models._empty_list)),
                ('retired_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_types', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_task_type',
                'constraints': [models.UniqueConstraint(fields=('tenant', 'kind', 'key'), name='uq_task_type_key')],
            },
        ),
    ]
