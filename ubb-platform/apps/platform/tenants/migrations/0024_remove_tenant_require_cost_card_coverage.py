from django.db import migrations


class Migration(migrations.Migration):
    """Remove Tenant.require_cost_card_coverage (#321, slice 3).

    The column was the opt-in that made an event UBB could not cost a 422
    instead of a recorded event, and it also gated a limited unit's start.
    #320 took the first meaning: the compute spine now records the event with
    its cost UNRESOLVED whatever this column said, so the flag bought nothing
    on the recording path. The start gate that survived was refusing work on a
    promise nothing keeps. Both go, and nothing replaces them — onboarding is
    not a wall, and a tenant part-way through declaring their cost rates gets
    their events recorded with the gaps named.

    REMOVED rather than defaulted off, so the wall cannot be turned back on.

    This follows the CURRENT head (0023) rather than renumbering onto shipped
    nodes: 0010 added the column and THREE later migrations depend on that node
    by name (usage/0021, customers/0012, tenants/0011). Renumbering would
    orphan all three.
    """

    dependencies = [
        ("tenants", "0023_rename_to_live_counter_maintenance_enabled"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tenant",
            name="require_cost_card_coverage",
        ),
    ]
