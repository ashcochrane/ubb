"""A money mode needs its payment rail activated first (G27, ADR-0008 §6).

`prepaid` and `postpaid` are the modes in which UBB moves a tenant's customer
money. ADR-0008 §6 makes entering one a separate act from platform admission:
a rail is activated for an environment by a named approver on recorded
evidence, and only then may a tenant use it. This migration lands the record
and the database's half of the rule.

1. **`ubb_payment_rail_activation`** — one row per rail and environment: the
   evidence (`rail`, `environment`, `activated_at`, `approved_by`,
   `evidence`) and the flag (`enabled`). Registry values and non-blank
   evidence are `CHECK`s.
2. **`trg_payment_rail_activation_declared_transitions`** — the five evidence
   columns are declared `FROZEN` (ADR-0007 §2): an activation is historical
   evidence and is never rewritten (the owner's ruling 2). `enabled` is left
   out on purpose — it is the operational switch. Beside it,
   **`trg_payment_rail_activation_is_kept`** refuses every `DELETE`: "no
   delete or revoke path" is a property of the table, not only of the admin
   (`PostingMeasurement`'s `BEFORE DELETE` rule is the precedent). A rail is
   withdrawn by its flag.
3. **`trg_tenant_money_mode_needs_its_rail`** — the backstop on `ubb_tenant`:
   a row may not ENTER `prepaid` or `postpaid` — be inserted in one, or have
   its mode or its environment change while in one — unless the rail has an
   enabled activation in the tenant's environment (a sandbox's is `test`,
   every other tenant's `live`; ruling 1). `Tenant.clean()` asks the same
   question first and answers it by name; this trigger is what a
   `QuerySet.update()`, a data migration or `psql` meets.

The flag is a column, so the database sees all of it: one rule holds the
record AND the flag, and G27 names the domain rule beside it for the named
refusal the API returns (ruling 3).

**No stored row is checked.** A tenant already in a money mode stays in it:
the rule governs entering one, and disabling a rail scans no dependent tenant
(ruling 2). UBB is deployed nowhere, so no live tenant is affected either way.

**Why `UPDATE OF billing_mode, is_sandbox` and a comparison inside.** Django's
`save()` writes every column, so the column list alone would fire on any save
of a money-mode tenant; the function returns at once when neither moved.

**The refusals are SQLSTATE 23000** — `IntegrityError`, like every other rule
of this kind in the tree — and each names what it holds.

**The reverse is exact**: drop the two rules and the table.
"""
import uuid

from django.db import migrations, models

FREEZE_TRIGGER = "trg_payment_rail_activation_declared_transitions"
FREEZE_FUNCTION = "ubb_payment_rail_activation_declared_transitions"
KEEP_TRIGGER = "trg_payment_rail_activation_is_kept"
KEEP_FUNCTION = "ubb_payment_rail_activation_is_kept"
BACKSTOP_TRIGGER = "trg_tenant_money_mode_needs_its_rail"
BACKSTOP_FUNCTION = "ubb_tenant_money_mode_needs_its_rail"

INSTALL = f"""
CREATE FUNCTION {FREEZE_FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER {FREEZE_TRIGGER}
BEFORE UPDATE ON ubb_payment_rail_activation
FOR EACH ROW
EXECUTE FUNCTION {FREEZE_FUNCTION}();

CREATE FUNCTION {KEEP_FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'a payment rail activation is never deleted: it is evidence of an '
        'approval that happened (ADR-0008 6). Disable the rail with its '
        'flag instead.'
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER {KEEP_TRIGGER}
BEFORE DELETE ON ubb_payment_rail_activation
FOR EACH ROW
EXECUTE FUNCTION {KEEP_FUNCTION}();

CREATE FUNCTION {BACKSTOP_FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER {BACKSTOP_TRIGGER}
BEFORE INSERT OR UPDATE OF billing_mode, is_sandbox ON ubb_tenant
FOR EACH ROW
WHEN (NEW.billing_mode IN ('prepaid', 'postpaid'))
EXECUTE FUNCTION {BACKSTOP_FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {BACKSTOP_TRIGGER} ON ubb_tenant;
DROP FUNCTION {BACKSTOP_FUNCTION}();
DROP TRIGGER {KEEP_TRIGGER} ON ubb_payment_rail_activation;
DROP FUNCTION {KEEP_FUNCTION}();
DROP TRIGGER {FREEZE_TRIGGER} ON ubb_payment_rail_activation;
DROP FUNCTION {FREEZE_FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0029_a_tenant_that_bills_elsewhere_is_external"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentRailActivation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rail", models.CharField(choices=[("stripe", "stripe")],
                                          max_length=20)),
                ("environment", models.CharField(
                    choices=[("live", "live"), ("test", "test")],
                    max_length=10)),
                ("activated_at", models.DateTimeField()),
                ("approved_by", models.CharField(max_length=255)),
                ("evidence", models.TextField()),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "ubb_payment_rail_activation",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("rail", "environment"),
                        name="uq_payment_rail_activation_once_per_environment"),
                    models.CheckConstraint(
                        condition=models.Q(rail__in=["stripe"]),
                        name="ck_payment_rail_activation_rail_known"),
                    models.CheckConstraint(
                        condition=models.Q(environment__in=["live", "test"]),
                        name="ck_payment_rail_activation_environment_known"),
                    models.CheckConstraint(
                        condition=models.Q(("approved_by", ""), _negated=True),
                        name="ck_payment_rail_activation_names_its_approver"),
                    models.CheckConstraint(
                        condition=models.Q(("evidence", ""), _negated=True),
                        name="ck_payment_rail_activation_carries_its_evidence"),
                ],
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
