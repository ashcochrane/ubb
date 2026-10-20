"""A price status carries its own reason (#603, ADR-0020).

`pricing_status_reason` is the registry's closed, nullable concept for *why a
pricing status applies* where a published reason does. Its one value,
`negative_price_unsupported`, sits beside an `unknown` price UBB calculated
exactly and the money rails cannot carry. NULL beside `unknown` is the ordinary
one — missing input — and NULL beside every other status is the only answer
there is.

Three operations, and the third is the one that needs its argument written down.

1. **The column**, nullable, with no default: every row that already exists
   carries no published reason, which is what NULL says. No row moves.
2. **Its closed set, and the combination rule widened to name it.** Only an
   `unknown` row may carry a reason; `known`, `waived` and `not_applicable` must
   carry NULL. The combination check is dropped and re-added rather than
   altered, because a `CHECK` has no `ALTER`; nothing in the table can fail the
   new one, since nothing has written the column yet.
3. **The price pair's transition rule (`0039`) widened to watch it.** The
   reason has no lifecycle of its own — it qualifies the status — so it is held
   by the same trigger as the pair: it may move only with the one permitted
   resolution, `unknown` to `known`, and that move must leave it NULL. On every
   other statement it is frozen, exactly as `not_applicable_reason` is. Without
   this a statement could relabel an `unknown` price's cause, or mark a price
   UBB could not resolve for want of a rule as one it calculated, and nothing
   would refuse it.

The function is REPLACED rather than added beside the old one, for the reason
`0039` gives for being a second trigger rather than a branch of the cost rule:
one rule per pair of columns, a `WHEN` clause naming only its own, and a drop
that leaves its neighbours standing. The reverse restores `0039`'s function and
`WHEN` clause exactly, then drops the checks and the column.

**The literals are frozen**, for the reason `0036` gives at length: a migration
records the schema as it was on the day it ran.
"""

from django.db import migrations, models

PRICING_STATUS_REASON = [
    ("negative_price_unsupported", "negative_price_unsupported"),
]

TRIGGER = "trg_posting_price_transitions"
FUNCTION = "ubb_posting_price_transitions"

#: The rule as 0039 left it, with the reason named in the condition and the
#: `WHEN` clause. Everything else is 0039's, word for word.
WIDENED = f"""
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
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER {TRIGGER} ON ubb_posting;
CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.billed_cost_micros IS DISTINCT FROM NEW.billed_cost_micros
      OR OLD.pricing_status IS DISTINCT FROM NEW.pricing_status
      OR OLD.not_applicable_reason IS DISTINCT FROM NEW.not_applicable_reason
      OR OLD.pricing_status_reason IS DISTINCT FROM NEW.pricing_status_reason)
EXECUTE FUNCTION {FUNCTION}();
"""

#: 0039's rule, restored by the reverse before the column it no longer names
#: is dropped.
AS_0039_LEFT_IT = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.billed_cost_micros IS DISTINCT FROM OLD.billed_cost_micros
       OR NEW.pricing_status IS DISTINCT FROM OLD.pricing_status
       OR NEW.not_applicable_reason IS DISTINCT FROM OLD.not_applicable_reason
    THEN
        IF OLD.pricing_status <> 'unknown'
           OR OLD.billed_cost_micros IS NOT NULL
           OR NEW.pricing_status <> 'known'
           OR NEW.billed_cost_micros IS NULL
           OR NEW.not_applicable_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unknown to known, completing the amount and moving the '
                'status in one statement; got % to %',
                OLD.pricing_status, NEW.pricing_status
                USING ERRCODE = '23000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER {TRIGGER} ON ubb_posting;
CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.billed_cost_micros IS DISTINCT FROM NEW.billed_cost_micros
      OR OLD.pricing_status IS DISTINCT FROM NEW.pricing_status
      OR OLD.not_applicable_reason IS DISTINCT FROM NEW.not_applicable_reason)
EXECUTE FUNCTION {FUNCTION}();
"""


def widen(apps, schema_editor):
    schema_editor.execute(WIDENED, params=None)


def restore(apps, schema_editor):
    schema_editor.execute(AS_0039_LEFT_IT, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0045_a_recording_keeps_what_its_acknowledgement_said"),
    ]

    operations = [
        # 1. The column. No row moves.
        migrations.AddField(
            model_name="posting",
            name="pricing_status_reason",
            field=models.CharField(blank=True, choices=PRICING_STATUS_REASON,
                                   max_length=32, null=True),
        ),
        # 2. Its closed set, at the database.
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pricing_status_reason__isnull", True),
                    ("pricing_status_reason__in",
                     ["negative_price_unsupported"]),
                    _connector="OR",
                ),
                name="ck_posting_pricing_status_reason",
            ),
        ),
        # 3. The combination rule, naming it: only `unknown` may carry one.
        #    Terms in `Q(**kwargs)`'s sorted order, for the reason 0038 gives.
        migrations.RemoveConstraint(
            model_name="posting",
            name="ck_posting_pricing_status_agrees_with_the_price",
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("billed_cost_micros__isnull", False),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "known"),
                             ("pricing_status_reason__isnull", True)),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "waived"),
                             ("pricing_status_reason__isnull", True)),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "unknown")),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", False),
                             ("pricing_status", "not_applicable"),
                             ("pricing_status_reason__isnull", True)),
                    _connector="OR",
                ),
                name="ck_posting_pricing_status_agrees_with_the_price",
            ),
        ),
        # 4. The transition rule, watching the reason too.
        migrations.RunPython(widen, restore),
    ]
