"""A customer price becomes known only through its door (#557).

`0039` made the price pair `RESOLVE_ONCE`: its one permitted move is `unknown`
to `known`, the amount and the status in one statement, and `0046` widened the
rule to hold the price status's own reason. That stops a second writer
CORRUPTING a posting. It does not stop one RESOLVING a posting — writing the
first price, which the rule admits from anyone — and then "this price is now
known" is decided in two places and tested in one
(`pricing/services/price_resolution.py`'s docstring has said so since #363).
The cost side answers that with an `ast` walk over the tree; the owner ruled the
price side's answer should be a behavioural or database rule instead
(#557, `5785065807`).

So the permitted move is admitted only on a statement the door marked:
`price_resolution.resolve_customer_price` sets the transaction-local setting
`ubb.price_door` to `resolve_customer_price` immediately before its one
`UPDATE` and clears it immediately after. Any other statement making the move —
`save()`, a queryset, raw SQL, a data migration — is refused with SQLSTATE
`23000`, as every rule on this table refuses, and its message names the rule's
class and column as every refusal here does (`usage/tests/_helpers.py` says why
a refusal naming less cannot be told from its neighbours'). Nothing else about
the rule moves:
the same columns, the same `WHEN` clause (so the trigger itself is not
re-created, only its function), the same other five conditions.

`current_setting(..., true)` answers NULL where the setting was never made, and
`IS DISTINCT FROM` reads a NULL as "not the door", so a session that never
heard of it is refused rather than let through.

**The literals are frozen**, for the reason `0036` gives at length. The reverse
re-installs `0046`'s function exactly, read from that migration rather than
copied, so the two cannot come to disagree about what `0046` installed.
"""
from importlib import import_module

from django.db import migrations

FUNCTION = "ubb_posting_price_transitions"

#: `0046`'s function, word for word, with the door's clause added after the
#: transition check — inside the same "a price column moved" branch, so a
#: statement that moves none of them is never asked.
WITH_THE_DOOR = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- billed_cost_micros and pricing_status are declared RESOLVE_ONCE AS A
    -- PAIR, and not_applicable_reason and pricing_status_reason move with
    -- them: the one permitted statement completes the amount and moves the
    -- status to known at once, from a posting whose price UBB could not
    -- resolve, and leaves both reasons NULL.
    --
    -- SIX conditions, FIVE of which a test drives directly:
    --   OLD.pricing_status <> 'unknown'  -- waived and not_applicable are
    --                                       terminal; known is a correction
    --   NEW.pricing_status <> 'known'    -- unknown does not become waived or
    --                                       not_applicable by relabelling
    --   NEW.billed_cost_micros IS NULL   -- half a resolution is not one
    --   NEW.not_applicable_reason IS NOT NULL  -- a priced row never carries
    --                                             a reason saying it has none
    --   NEW.pricing_status_reason IS NOT NULL  -- nor one saying why it was
    --                                             unknown (#603)
    --
    -- The sixth, OLD.billed_cost_micros IS NOT NULL, is DEFENCE IN DEPTH, as
    -- 0039 argues: no committed `unknown` row can reach it past the CHECK.
    IF NEW.billed_cost_micros IS DISTINCT FROM OLD.billed_cost_micros
       OR NEW.pricing_status IS DISTINCT FROM OLD.pricing_status
       OR NEW.not_applicable_reason IS DISTINCT FROM OLD.not_applicable_reason
       OR NEW.pricing_status_reason IS DISTINCT FROM OLD.pricing_status_reason
    THEN
        IF OLD.pricing_status <> 'unknown'
           OR OLD.billed_cost_micros IS NOT NULL
           OR NEW.pricing_status <> 'known'
           OR NEW.billed_cost_micros IS NULL
           OR NEW.not_applicable_reason IS NOT NULL
           OR NEW.pricing_status_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unknown to known, completing the amount and moving the '
                'status in one statement; got % to %',
                OLD.pricing_status, NEW.pricing_status
                USING ERRCODE = '23000';
        END IF;
        -- AND THE PERMITTED MOVE IS THE DOOR'S ALONE (#557).
        IF current_setting('ubb.price_door', true)
           IS DISTINCT FROM 'resolve_customer_price' THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once, and a customer price becomes known only '
                'through its door, price_resolution.resolve_customer_price '
                '(#557): this statement resolved one without the mark that '
                'door sets'
                USING ERRCODE = '23000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


def install(apps, schema_editor):
    schema_editor.execute(WITH_THE_DOOR, params=None)


def restore(apps, schema_editor):
    previous = import_module(
        "apps.metering.usage.migrations."
        "0046_the_price_status_carries_its_own_reason")
    schema_editor.execute(previous.WIDENED, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0048_an_event_type_with_no_publication_is_a_reason"),
    ]

    operations = [
        migrations.RunPython(install, restore),
    ]
