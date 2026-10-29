"""The tenants app's database rules: the triggers no model declaration can hold.

Part of the fresh initial set the cutover regenerated (#190; ADR-0026). The schema
migration beside this one is generated from the final models; these rules are not
in Django's migration state, so they are carried here by hand. Each one is the
final installed definition the old migration chain left, carried exactly: the
function bodies are byte-for-byte the last installer's, and the refusal texts,
vocabulary literals and SQL aliases that tests compare are unchanged. Each
constant names the historical migration whose text it carries.

Every rule refuses with SQLSTATE 23000. Each statement is passed to `RunSQL` as a
list item so it runs verbatim — a plain string would be split and comment-stripped
by `sqlparse`, which would change the stored function bodies.

DEPENDENCIES (§0.3 point 1): this migration depends on the schema leaf of every
app owning a table its SQL references, never on an assumed `0001`:
  trg_payment_rail_activation_declared_transitions: ubb_payment_rail_activation (tenants)
  trg_payment_rail_activation_is_kept: ubb_payment_rail_activation (tenants)
  trg_tenant_money_mode_needs_its_rail: ubb_tenant (tenants), ubb_payment_rail_activation (tenants)
"""
from django.db import migrations


#: A payment rail activation's evidence is frozen.
#: Carried from tenants/0030_a_money_mode_needs_its_payment_rail.
PAYMENT_RAIL_ACTIVATION_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_payment_rail_activation_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    moved text[];
BEGIN
    -- What was approved, where, when, by whom and on what evidence is
    -- history. The flag beside it may move; these never do.
    SELECT array_agg(changed.key ORDER BY changed.key) INTO moved
    FROM (
        SELECT after.key
        FROM jsonb_each(to_jsonb(NEW)) AS after(key, value)
        JOIN jsonb_each(to_jsonb(OLD)) AS before(key, value)
          ON before.key = after.key
        WHERE after.value IS DISTINCT FROM before.value
          AND after.key = ANY (ARRAY['rail', 'environment', 'activated_at',
                                     'approved_by', 'evidence'])
    ) AS changed;

    IF moved IS NOT NULL THEN
        RAISE EXCEPTION
            'these columns of ubb_payment_rail_activation are declared frozen '
            '(ADR-0007 2): %. An activation is evidence of an approval that '
            'happened; disable the rail with its flag rather than rewriting '
            'what was approved.',
            array_to_string(moved, ', ')
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_payment_rail_activation_declared_transitions
BEFORE UPDATE ON ubb_payment_rail_activation
FOR EACH ROW
EXECUTE FUNCTION ubb_payment_rail_activation_declared_transitions();
"""

#: A payment rail activation is never deleted.
#: Carried from tenants/0030_a_money_mode_needs_its_payment_rail.
PAYMENT_RAIL_ACTIVATION_IS_KEPT = """
CREATE FUNCTION ubb_payment_rail_activation_is_kept() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'a payment rail activation is never deleted: it is evidence of an '
        'approval that happened (ADR-0008 6). Disable the rail with its '
        'flag instead.'
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER trg_payment_rail_activation_is_kept
BEFORE DELETE ON ubb_payment_rail_activation
FOR EACH ROW
EXECUTE FUNCTION ubb_payment_rail_activation_is_kept();
"""

#: A money mode needs its payment rail (G27's database backstop).
#: Carried from tenants/0030_a_money_mode_needs_its_payment_rail.
TENANT_MONEY_MODE_NEEDS_ITS_RAIL = """
CREATE FUNCTION ubb_tenant_money_mode_needs_its_rail() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    wanted text := CASE WHEN NEW.is_sandbox THEN 'test' ELSE 'live' END;
BEGIN
    -- Entering a money mode, not being in one: a re-save that moves neither
    -- the mode nor the environment asks nothing (no dependent-tenant scan).
    IF TG_OP = 'UPDATE'
       AND NEW.billing_mode IS NOT DISTINCT FROM OLD.billing_mode
       AND NEW.is_sandbox IS NOT DISTINCT FROM OLD.is_sandbox THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM ubb_payment_rail_activation
        WHERE rail = 'stripe' AND environment = wanted AND enabled
    ) THEN
        RAISE EXCEPTION
            'payment_rail_not_activated: billing_mode % needs the stripe '
            'payment rail activated and enabled in its % environment '
            '(ADR-0008 6, G27)',
            NEW.billing_mode, wanted
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tenant_money_mode_needs_its_rail
BEFORE INSERT OR UPDATE OF billing_mode, is_sandbox ON ubb_tenant
FOR EACH ROW
WHEN (NEW.billing_mode IN ('prepaid', 'postpaid'))
EXECUTE FUNCTION ubb_tenant_money_mode_needs_its_rail();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [PAYMENT_RAIL_ACTIVATION_DECLARED_TRANSITIONS],
            [_uninstall("trg_payment_rail_activation_declared_transitions", "ubb_payment_rail_activation", "ubb_payment_rail_activation_declared_transitions")],
        ),
        migrations.RunSQL(
            [PAYMENT_RAIL_ACTIVATION_IS_KEPT],
            [_uninstall("trg_payment_rail_activation_is_kept", "ubb_payment_rail_activation", "ubb_payment_rail_activation_is_kept")],
        ),
        migrations.RunSQL(
            [TENANT_MONEY_MODE_NEEDS_ITS_RAIL],
            [_uninstall("trg_tenant_money_mode_needs_its_rail", "ubb_tenant", "ubb_tenant_money_mode_needs_its_rail")],
        ),
    ]
