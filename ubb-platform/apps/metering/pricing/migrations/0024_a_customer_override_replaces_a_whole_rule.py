"""A customer override replaces a whole rule, method included (#361, #151 §6).

**The column.** A Pricing Book may now name the customer whose own pricing
rules it holds. A book carrying a customer is that customer's OVERRIDE book and
resolution reads its rules at the ladder's customer's-own source; a book
carrying none is a catalogue the tenant wrote for everybody.

**ADDITIVE, AND IT RENAMES NOTHING.** No column moves, no data is copied and no
row changes meaning. Every book in the tree is nobody's until a tenant declares
an override, which is the honest reading rather than a backfill left undone:
UBB ships no negotiated deals.

**WHY THE CUSTOMER SITS ON THE BOOK AND NOT ON THE RULE.** An override is a
complete rule — its method, its terms and the selectors it pins all its own —
so it is written where rules are written and published the way rules are
published. A book is what a publish record changes, what `uq_rate_active_in_book`
scopes uniqueness to and what `plan_changes` resolves a change against. Scoping
rules to a customer INSIDE a shared book would put the customer into a rule's
IDENTITY and move all three at once; putting it on the book moves none of them.

⚠ **THAT IS A CLAIM ABOUT RULE IDENTITY, NOT ABOUT THE WHOLE PUBLISH PATH.**
`plan_changes` IS edited by this commit — a change body may now state a rule's
method — but that is an additive extension of what a body carries, not a change
to how a rule is identified, closed or reopened. What is untouched is the part
an override depends on: `_identity_of_rule`, the uniqueness rule above, and the
publish, forward-dating and reversal path, none of which knows a customer
exists.

**`SET_NULL`, BECAUSE `Rate.rate_card` IS `PROTECT`.** Cascading a customer's
deletion into their book would make the database refuse to delete any customer
who was ever given a negotiated price, from a record nobody deleting a customer
asked about — the shape that stops a tenant wipe half way (#354, #358). Nulling
it leaves the rules, their windows and the receipts pointing at them untouched.

**The constraint.** One override book per customer per currency: two would be
two answers at one rung with nothing deciding between them.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_customer_suspension_reason'),
        ('pricing', '0023_every_change_to_a_book_is_a_publish'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.AddField(
            model_name='ratecard',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pricing_override_books', to='customers.customer'),
        ),
        migrations.AddConstraint(
            model_name='ratecard',
            constraint=models.UniqueConstraint(condition=models.Q(('customer__isnull', False)), fields=('customer', 'currency'), name='uq_pricing_book_one_override_per_customer'),
        ),
    ]
