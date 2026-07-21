# Two-secret overlap rotation (#83): add the retiring-secret fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0004_tenantwebhookconfig_uq_webhook_config_tenant_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantwebhookconfig',
            name='retiring_secret',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Previous signing secret, still emitted while its '
                          'overlap window is open. Empty once no rotation is in '
                          'flight.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='tenantwebhookconfig',
            name='retiring_secret_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
