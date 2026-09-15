"""A tenant that bills its customers somewhere other than UBB may state what
it earned from one of them over one period (#495, slice 7 §9).

One table, and it is a BUILD rather than an extension. #153 §3.3 says the
recurring revenue profile beside it is *replaced*, not widened, and the reasons
are structural: one recurring amount per customer, no per-period rows, no
source reference, and — decisively — an amount summed into the same column as a
Stripe subscription, so the provenance of a revenue figure was destroyed the
moment it landed and no surface could say where the number came from.

⚠ **NOTHING IS CARRIED HERE AND THAT IS NOT ADR-0007 §1 BEING SKIPPED.** This
migration moves no column and renames nothing: it creates a table beside the
profile, which stays exactly as it is and keeps every row it holds. The ticket
that retires the profile is the one that owes the carry, and it is the next one
in this slice.

⚠ **AND NO ROW OF THIS TABLE IS A CHARGE.** `pricing.Charge` records what UBB
charged a customer for a delivered piece of work. This records what a tenant
says it collected in a system UBB does not operate, admitted so that margin can
be computed at the scope the figure was supplied at. The two never meet, and no
surface may present one as the other.

**THE FOUR CHECKS, EACH REFUSING SOMETHING DIFFERENT:**

* the recognition method is one the registry declares — a value set belongs at
  the database, where a data migration and a shell both meet it, rather than in
  `choices=`, which is a form-layer courtesy;
* a span that closes opens first, `period_end` being exclusive and nullable for
  revenue that is an instant rather than a stretch of time;
* a method that spreads an amount across a span has a span to spread it across,
  so the method can never fall back to a shape the record did not state — every
  such fallback is the unlabelled proration this record exists to end;
* a supplied figure says where it came from. `source_reference` must carry a
  non-space character — not merely a non-empty string, because three spaces
  satisfy `<> ''` and say nothing — since a number whose source is unstated is
  the thing being replaced.

**THE UNIQUENESS KEY IS THE RECORD'S RULE**: one row per customer per
period-open per source reference. Stating the same period from the same source
again re-states the figure — the same act, audited each time under
`tenant_supplied_revenue.recorded` — while a different source reference adds a
figure beside it, because two invoices covering one month are two facts rather
than a contradiction.

**THE REVERSE IS EXACT**: drop the table. Nothing else is touched, because
nothing else was.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0013_the_monthly_totals_count_what_they_could_not_price'),
        ('customers', '0014_customer_suspension_reason'),
        ('tenants', '0027_admission_control_comes_to_the_kernel'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantSuppliedRevenue',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount_micros', models.BigIntegerField()),
                ('currency', models.CharField(max_length=3)),
                ('period_start', models.DateField()),
                ('period_end', models.DateField(blank=True, null=True)),
                ('recognition_method', models.CharField(
                    choices=[('on_receipt', 'on_receipt'),
                             ('straight_line', 'straight_line')],
                    max_length=32)),
                ('source_reference', models.CharField(max_length=255)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='supplied_revenue', to='customers.customer')),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='supplied_revenue', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_tenant_supplied_revenue',
                'indexes': [models.Index(
                    fields=['tenant', 'customer', 'period_start'],
                    name='idx_supplied_revenue_window')],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('tenant', 'customer', 'period_start',
                                'source_reference'),
                        name='uq_supplied_revenue_period_source'),
                    models.CheckConstraint(
                        condition=models.Q(
                            ('recognition_method__in',
                             ['on_receipt', 'straight_line'])),
                        name='ck_supplied_revenue_known_method'),
                    models.CheckConstraint(
                        condition=models.Q(
                            ('period_end__isnull', True),
                            ('period_end__gt', models.F('period_start')),
                            _connector='OR'),
                        name='ck_supplied_revenue_span_opens_before_it_closes'),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(('recognition_method', 'straight_line'),
                                     _negated=True),
                            ('period_end__isnull', False),
                            _connector='OR'),
                        name='ck_supplied_revenue_straight_line_has_a_span'),
                    models.CheckConstraint(
                        condition=models.Q(('source_reference__regex', '\\S')),
                        name='ck_supplied_revenue_says_where_it_came_from'),
                ],
            },
        ),
    ]
