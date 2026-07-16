# The clean cut (one-rule enforcement spec, issue #37): run -> task on every
# surface at once. Plain rename migrations — no live tenant exists, so there
# are no data concerns (spec §A).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0003_run_idx_run_owner_status"),
        # Every historical migration that references the pre-rename model
        # ('tasks.run' — usage's FK adds) must apply BEFORE the rename, or
        # the graph can order them after it and fail to resolve the model.
        ("usage", "0025_widen_rawingestevent_idempotency_key"),
    ]

    operations = [
        migrations.RenameModel(old_name="Run", new_name="Task"),
        migrations.AlterModelTable(name="task", table="ubb_task"),
        # total_cost_micros (billed-only) splits into two explicit totals.
        migrations.RenameField(
            model_name="task",
            old_name="total_cost_micros",
            new_name="total_billed_cost_micros",
        ),
        migrations.AddField(
            model_name="task",
            name="total_provider_cost_micros",
            field=models.BigIntegerField(default=0),
        ),
        # The limit is COGS-denominated now: provider cost, never billed.
        migrations.RenameField(
            model_name="task",
            old_name="cost_limit_micros",
            new_name="provider_cost_limit_micros",
        ),
        # "Hard stop" vocabulary retired with the 429.
        migrations.RenameField(
            model_name="task",
            old_name="hard_stop_balance_micros",
            new_name="floor_snapshot_micros",
        ),
        migrations.RenameField(
            model_name="task",
            old_name="external_run_id",
            new_name="external_task_id",
        ),
        # The label column dies with the label-cap machinery; tags are
        # analytics-only and the UsageEvent.task FK is the only attribution.
        migrations.RemoveField(model_name="task", name="task_id"),
        migrations.RenameIndex(
            model_name="task",
            old_name="idx_run_customer_created",
            new_name="idx_task_customer_created",
        ),
        migrations.RenameIndex(
            model_name="task",
            old_name="idx_run_tenant_status",
            new_name="idx_task_tenant_status",
        ),
        migrations.RenameIndex(
            model_name="task",
            old_name="idx_run_status_heartbeat",
            new_name="idx_task_status_heartbeat",
        ),
        migrations.RenameIndex(
            model_name="task",
            old_name="idx_run_owner_status",
            new_name="idx_task_owner_status",
        ),
        # related_name runs -> tasks (state-only).
        migrations.AlterField(
            model_name="task",
            name="tenant",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="tasks",
                to="tenants.tenant",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="customer",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="tasks",
                to="customers.customer",
            ),
        ),
    ]
