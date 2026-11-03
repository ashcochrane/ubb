"""The subscriptions app's database rules: the triggers no model declaration can hold.

R10 Stage C2 (PLAN §7 item 27): a subscription invoice's historical billing owner
is declared FROZEN (`SubscriptionInvoice.transition_classes`), and this rule is
what keeps the declaration — a `BEFORE UPDATE` trigger refusing any change to
`billing_owner_id`, through `save()`, `QuerySet.update()` and raw SQL alike. A
model-level guard is not enforcement and is never shipped as one (ADR-0007 §2).
The column itself is added by the schema migration beside this one,
`0002_subscriptioninvoice_billing_owner`; these rules are not in Django's
migration state, so they are carried here by hand, in the one home a table's
triggers have.

The rule refuses with SQLSTATE 23000. The statement is passed to `RunSQL` as a
list item so it runs verbatim — a plain string would be split and
comment-stripped by `sqlparse`, which would change the stored function body.

DEPENDENCIES (§0.3 point 1): this migration depends on the schema leaf of every
app owning a table its SQL references, never on an assumed `0001`:
  trg_subscription_invoice_declared_transitions: ubb_subscription_invoice (subscriptions)
"""
from django.db import migrations


#: A subscription invoice's historical billing owner is frozen.
#: Written for R10 Stage C2 (PLAN §7 item 27).
SUBSCRIPTION_INVOICE_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_subscription_invoice_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- billing_owner_id is declared FROZEN: it is the billing owner UBB resolved
    -- for this invoice when the invoice first entered UBB, and a later change of
    -- customer topology never moves which owner an unresolved payment failure
    -- counts against. It is set once, by the row's INSERT, and never rewritten.
    IF NEW.billing_owner_id IS DISTINCT FROM OLD.billing_owner_id THEN
        RAISE EXCEPTION
            'billing_owner_id is declared frozen (ADR-0007 §2): the historical '
            'billing owner of a subscription invoice is fixed when the invoice '
            'enters UBB and is never rewritten (R10 Stage C2). Got % to %',
            OLD.billing_owner_id, NEW.billing_owner_id
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_subscription_invoice_declared_transitions
BEFORE UPDATE ON ubb_subscription_invoice
FOR EACH ROW
WHEN (OLD.billing_owner_id IS DISTINCT FROM NEW.billing_owner_id)
EXECUTE FUNCTION ubb_subscription_invoice_declared_transitions();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0002_subscriptioninvoice_billing_owner"),
    ]

    operations = [
        migrations.RunSQL(
            [SUBSCRIPTION_INVOICE_DECLARED_TRANSITIONS],
            [_uninstall("trg_subscription_invoice_declared_transitions",
                        "ubb_subscription_invoice",
                        "ubb_subscription_invoice_declared_transitions")],
        ),
    ]
