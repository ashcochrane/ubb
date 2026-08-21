"""The plan catalog's two markup columns are deleted (#369, spec §6).

**WHAT GOES.** A percentage — millionths of a percent under a money suffix — and
a per-event flat addend, both on the Plan row, both read by metering as the
middle rung of the price ladder.

**WHAT REPLACED THEM.** The plan's required Pricing Book reference, added in
`0002` (#362). A plan prices its customers from the rules in the book it names,
on records that say which quantity they price; a percentage on a catalogue row
could say only its own value. Where that book prices nothing, the answer falls
to the tenant's declared default markup rung (#357) or, where the tenant has
declared none, to `unknown` — which is a price nobody has stated, with no amount
at all.

⚠ **THAT LAST OUTCOME IS NEW, AND IT IS THE POINT.** `markup_percentage_micros`
defaulted to `0`, so a plan ALWAYS supplied a rung and a customer on a plan could
never reach `unknown`: "the tenant said nothing" was served as "the tenant said
zero", which is a settled charge of exactly what the call cost. Deleting the
column is what makes the honest answer reachable.

⚠ **THERE IS NO BACKFILL AND NO HEURISTIC, AND THAT IS A DECISION RATHER THAN AN
OMISSION.** #147 §4.3 and #155 flagged that a migration cannot distinguish a
plan's ABSENT markup from a DELIBERATE ZERO, because both are `0` in the column
— so any conversion would have to guess which plans meant which. That is moot in
practice: **UBB is deployed nowhere and holds no tenant data**, and #155 §11
squashes every migration at cutover, so the fresh initial set will create
`ubb_plan` without these columns and with nothing to carry. A tenant who wanted
the old behaviour declares a markup rung, which is one route call and is not a
guess.

**THE PERCENTAGE IS DELETED RATHER THAN RENAMED, AND ITS LEDGER ENTRY IS PAID BY
THAT.** The G11 entry over this column records an `expected` value that is a
new spelling (`markup_micro_percent`), because the column hid millionths of a
percent under `_micros`. Its own `reason` says the payment is deletion: a rename
would have moved the honest spelling onto a column with no reader left. The
spelling was taken instead on `TenantDefaultMarkup.markup_micro_percent`, where
it cost nothing.

⚠ **HAND-WRITTEN, for the reason every rename migration in this programme
gives.** `makemigrations` only asks "did you rename this?" on a TTY, so a
non-interactive run writes the add-plus-remove pair ADR-0007 §1 forbids,
silently. Nothing here was generated.

**THE REVERSE IS DJANGO'S OWN INVERSE AND NOTHING HERE RUNS PYTHON.** There is
no `RunPython`, so the convention asking for a hand-written reverse a test
exercises (`docs/conventions/django-patterns.md`) does not bind: each removed
column comes back at the definition the state above holds. ⚠ What no inverse
restores is DATA — the values go with the columns. Stated rather than papered
over: this tree is deployed nowhere.

⚠ **THIS FILE NAMES NO RETIRED TERM EITHER.** The migrations tree is a declared
sweep exclusion covering every migration directory wholesale
(`gates/forbidden-term-sweep.yaml`), so any new migration lifts
`historical-migrations` by one whatever it spells. The unit collision these
columns carried is **G11**, a naming gate over model COLUMNS, and G11 is not
sweep input.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0002_a_plan_names_the_book_it_prices_from'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plan',
            name='markup_percentage_micros',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='fixed_uplift_micros',
        ),
    ]
