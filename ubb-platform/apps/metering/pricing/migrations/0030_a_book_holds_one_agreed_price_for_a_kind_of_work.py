"""A Pricing Book grows a second kind of line: one agreed price for a whole
delivered unit of work of a named kind (#415, #139 §2.4).

Every revenue line in this schema has priced a measured QUANTITY — so much per
thousand tokens, so much per rendered second. A tenant who sells a whole piece
of work for one agreed number has had nowhere to put that number, and the two
workarounds are both wrong: reverse-engineering a per-unit rate that happens to
sum to the quote fails because how much work the delivery takes is not knowable
when the price is agreed, and holding the amount on the declaration of the kind
of work re-opens what #138 settled for the Event Type.

**IT IS A LINE IN THE CUSTOMER'S OWN POLICY BOOK, WHICH IS WHERE EVERY OTHER
PRICE ALREADY LIVES.** That is the whole of the placement argument: per-customer
pricing, book selection and the tenant's existing publishing model come with it,
and a tenant has one place to look and one place to change. A second
configuration surface for money would have none of that.

**THE LADDER INSIDE A BOOK IS ONE STEP.** A rate's ladder — the exact Event
Type, then a broader rule, then the book's own default — is about events. This
keys on the kind of work and on nothing else, so there is no narrower line to
out-rank a broader one and no book-wide fallback beneath either: *a default
agreed price for all work regardless of kind* is not something a tenant could
mean. What ranks is which BOOK the line came from, which is the ladder the
Pricing Book side already has.

**PURE ADDITION.** No column moves, no row is rewritten and nothing existing
reads this table; the reverse drops it. `ck_task_price_amount_not_negative`
admits zero deliberately — a tenant may agree to deliver a kind of work for
nothing, and only a number below zero is a sign error rather than a deal.
`uq_task_price_active_in_pricing_book` is what stops one book holding two open
lines for one kind of work, which would be two answers with nothing to choose
between them.
"""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0029_the_markup_record_is_deleted'),
        ('tenants', '0025_the_two_expiry_windows_get_a_tenant_rung'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskPrice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('task_type', models.CharField(max_length=64)),
                ('amount_micros', models.BigIntegerField()),
                ('valid_from', models.DateTimeField(
                    db_index=True, default=django.utils.timezone.now)),
                ('valid_to', models.DateTimeField(blank=True, null=True)),
                ('pricing_book', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='task_prices', to='pricing.pricingbook')),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='task_prices', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_task_price',
                'indexes': [models.Index(fields=['task_type', 'valid_from'],
                                         name='idx_task_price_lookup')],
                'constraints': [
                    models.UniqueConstraint(
                        condition=models.Q(('valid_to__isnull', True)),
                        fields=('pricing_book', 'task_type'),
                        name='uq_task_price_active_in_pricing_book'),
                    models.CheckConstraint(
                        condition=models.Q(('amount_micros__gte', 0)),
                        name='ck_task_price_amount_not_negative'),
                ],
            },
        ),
    ]
