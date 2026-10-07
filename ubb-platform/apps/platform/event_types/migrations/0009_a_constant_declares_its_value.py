"""A constant Measurement declares its value (#571).

One nullable text column and three rules: a constant owes its value and only a
constant may carry one; the value is in its one canonical exact-decimal form;
and under an `integer` declaration it is whole. The canonical grammar is
spelled out below rather than imported from `exact_decimals.py`, because a
migration describes the tree as it was on the day it was written.

**Between the column and the rules, a guard that REFUSES and never invents.**
Before this migration a constant had nowhere to hold its value, so every
constant quantity already declared is one without a value, and the first rule
would refuse it. Supplying a value is not this migration's to do: a constant's
value is a commercial statement the tenant makes, and a made-up one — zero,
one, anything — would be a number on a declaration that nobody declared. So
the guard names every such quantity, and every kept publication pinning one,
and stops. UBB is deployed nowhere, so on the day this was written there was
nothing for it to find; it is what makes refusing a valueless constant at the
declare door honest rather than an assumption about the tree.

**Kept publications are not rewritten.** A copy `publish` kept before this has
no `constant_value` key at all, and its read answers `None` for it
(`publication.py`). The guard is what makes that true: it refuses to run over
any copy pinning a constant, so every quantity a surviving copy holds is one
of another kind, whose value is `None`.

The reverse removes the rules and the column, and with the column every
declared value: a constant goes back to having nowhere to hold one, which is
the tree the reverse returns to.
"""
from django.db import migrations, models

SOURCE_KIND_CONSTANT = "constant"


class ConstantWithoutAValue(Exception):
    """A constant quantity holds no value, and the rules about to be added
    would refuse it. The guard says which, rather than letting a constraint
    violation say nothing."""


def refuse_a_constant_without_a_value(apps, schema_editor):
    """Name every constant without a value, by everything it takes to find it
    — the tenant's id and name, the Event Type's key, the quantity's code,
    and the row itself — and stop. It repairs nothing: the value is the
    tenant's to declare, and a pre-launch configuration is theirs to change
    or reset."""
    EventType = apps.get_model("event_types", "EventType")
    Measurement = apps.get_model("event_types", "Measurement")

    found = [
        f"declared quantity '{code}' (Measurement {pk}) under Event Type "
        f"'{key}' of tenant {tenant_id} ('{tenant_name}')"
        for pk, tenant_id, tenant_name, key, code in (
            Measurement.objects
            .filter(source_kind=SOURCE_KIND_CONSTANT,
                    constant_value__isnull=True)
            .order_by("event_type__tenant_id", "event_type__key", "code")
            .values_list("pk", "event_type__tenant_id",
                         "event_type__tenant__name", "event_type__key",
                         "code"))]
    kept = (EventType.objects.filter(published_declaration__isnull=False)
            .order_by("tenant_id", "key")
            .values_list("pk", "tenant_id", "tenant__name", "key",
                         "published_declaration"))
    for pk, tenant_id, tenant_name, key, pinned in kept:
        for quantity in pinned.get("measurements") or ():
            if (quantity.get("source_kind") == SOURCE_KIND_CONSTANT
                    and quantity.get("constant_value") is None):
                found.append(
                    f"kept publication of Event Type '{key}' (EventType "
                    f"{pk}) of tenant {tenant_id} ('{tenant_name}'), pinning "
                    f"quantity '{quantity.get('code')}'")
    if found:
        raise ConstantWithoutAValue(
            f"event_types 0009 refuses to run: {len(found)} constant "
            f"quantit{'y holds' if len(found) == 1 else 'ies hold'} no value, "
            f"and from this migration on a constant's value is part of its "
            f"declaration. UBB never invents one, and repairs nothing. Found: "
            f"{'; '.join(found)}. For each, with the build BEFORE this "
            f"migration's (this build's routes read the column it adds): "
            f"withdraw the quantity (DELETE "
            f"/api/v1/event-types/<key>/measurements/<code>) or re-declare it "
            f"as another source kind, then publish its Event Type again (POST "
            f"/api/v1/event-types/<key>/publish) so that no kept publication "
            f"pins it — or, for a sandbox tenant, reset its configuration "
            f"(POST /api/v1/sandbox/reset with keep_config false). Then "
            f"migrate, and declare the constant with its value.")


class Migration(migrations.Migration):

    dependencies = [
        ('event_types', '0008_the_value_type_is_read_off_the_registry'),
    ]

    operations = [
        migrations.AddField(
            model_name='measurement',
            name='constant_value',
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.RunPython(refuse_a_constant_without_a_value,
                             migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='measurement',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('constant_value__isnull', False), ('source_kind', 'constant')), models.Q(models.Q(('source_kind', 'constant'), _negated=True), ('constant_value__isnull', True)), _connector='OR'), name='ck_measurement_constant_value_iff_constant'),
        ),
        migrations.AddConstraint(
            model_name='measurement',
            constraint=models.CheckConstraint(condition=models.Q(('constant_value__isnull', True), ('constant_value__regex', '^(0|-?(0\\.[0-9]*[1-9]|[1-9][0-9]*(\\.[0-9]*[1-9])?))$'), _connector='OR'), name='ck_measurement_constant_value_is_canonical'),
        ),
        migrations.AddConstraint(
            model_name='measurement',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('value_type', 'integer'), _negated=True), ('constant_value__isnull', True), models.Q(('constant_value__contains', '.'), _negated=True), _connector='OR'), name='ck_measurement_integer_constant_is_whole'),
        ),
    ]
