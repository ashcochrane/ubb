"""The tenant-level markup record is deleted (#369, spec §6, §19).

**WHAT GOES.** One table held two kinds of row, told apart by whether a customer
was on it: the row with none was the tenant's default markup, and a row with one
was that customer's override. Both were a percentage — stored as millionths of a
percent under a money suffix — plus a per-event flat addend, and both were read
as rungs of the price ladder.

**WHAT REPLACED EACH ROW, AND WHY NEITHER IS A RENAME.**

  * the tenant-default row became `ubb_tenant_default_markup` in `0024`
    (#357) — a DECLARED record with one column, its own routes and its own two
    audit actions, rather than a rung read out of an absence. It has been the
    rung that prices unruled events since that migration; the row here has
    priced nothing since;
  * a customer's override became a RULE in that customer's own Pricing Book
    (#361) — a whole rule, with a method and the quantity it prices, declared
    and published like any other. A percentage on a configuration row could not
    say what it applied to.

So this is a deletion, not a conversion. Both replacements were built and are in
use before this migration runs, which is the ordering the ticket chain forces.

⚠ **THERE IS NO BACKFILL AND NO HEURISTIC, AND THAT IS A DECISION RATHER THAN AN
OMISSION.** Two documents flagged that a migration cannot distinguish an ABSENT
markup from a DELIBERATE ZERO, because both are `0` in the column (#147 §4.3,
#155). That is moot in practice: **UBB is deployed nowhere and holds no tenant
data**, and #155 §11 squashes every migration at cutover, so the fresh initial
set will create `ubb_tenant_default_markup` alone with nothing to carry.
Writing a converter would be writing, testing and reviewing a guess for zero
rows, and then deleting it. Any row that did exist would be answered by the
tenant declaring their rung, which is one route call and is not a guess.

⚠ **HAND-WRITTEN, for the reason `0016`, `0026`, `0027` and `0028` all give.**
`makemigrations` only asks "did you rename this?" on a TTY, so a non-interactive
run writes the add-plus-remove pair ADR-0007 §1 forbids, silently. Nothing here
was generated. There is no rename in this file to miss — but the discipline is
the file's, not the operation's, and a half-generated migration is worse than
either kind.

**THE REVERSE IS DJANGO'S OWN INVERSE AND NOTHING HERE RUNS PYTHON.** There is
no `RunPython`, so the convention asking for a hand-written reverse a test
exercises (`docs/conventions/django-patterns.md`) does not bind: `DeleteModel`
reverses by recreating the table from the state above it, with its columns and
both of its partial uniqueness keys. ⚠ What no inverse restores is DATA — every
row goes with the table. Stated rather than papered over: this tree is deployed
nowhere and the table is empty.

⚠ **THIS FILE NAMES NO RETIRED TERM, AND THE EXCLUSION IT MOVES IS NOT ABOUT
THAT.** The migrations tree is a declared sweep exclusion covering every
migration directory wholesale (`gates/forbidden-term-sweep.yaml`), so ANY new
migration lifts `historical-migrations` by one whatever it spells — which is why
that count moves by two for this commit and no G7 ledger entry moves with it.
The unit collision this record carried is **G11**, a naming gate over model
COLUMNS, and G11 is not sweep input: `markup_percentage_micros` was never a
retired token, so nothing here needed excusing.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0028_the_container_becomes_a_pricing_book_and_a_cost_book'),
    ]

    operations = [
        # THE TWO PARTIAL KEYS COME OFF FIRST. They are what made the table two
        # record kinds in one — one row per tenant with no customer, one row per
        # (tenant, customer) with one — and Django's state may not hold a
        # constraint over a model it is about to drop. Dropping the table would
        # take them with it either way; naming them here is what keeps the
        # reverse able to put both back.
        migrations.RemoveConstraint(
            model_name='tenantmarkup',
            name='uq_markup_tenant_default',
        ),
        migrations.RemoveConstraint(
            model_name='tenantmarkup',
            name='uq_markup_tenant_customer',
        ),
        migrations.DeleteModel(
            name='TenantMarkup',
        ),
    ]
