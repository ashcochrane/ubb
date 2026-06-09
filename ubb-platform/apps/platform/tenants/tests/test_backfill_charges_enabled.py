import pytest

from django.db import connection

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
def test_backfill_marks_connected_tenants_charge_ready():
    """Tenants with an existing connected account must be charge-ready after backfill.

    Simulates the pre-migration state (charges_enabled=False on a tenant that
    already has stripe_connected_account_id set) then replays the exact SQL from
    0012_backfill_charges_enabled and asserts only the connected tenant flips.
    """
    t_connected = Tenant.objects.create(
        name="C", products=["metering"], stripe_connected_account_id="acct_x"
    )
    # Simulate pre-backfill state: field exists but is still False
    Tenant.objects.filter(id=t_connected.id).update(charges_enabled=False)

    t_none = Tenant.objects.create(name="N", products=["metering"])

    # Replay the backfill SQL from the migration
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE ubb_tenant SET charges_enabled = TRUE "
            "WHERE stripe_connected_account_id IS NOT NULL "
            "AND stripe_connected_account_id != ''"
        )

    t_connected.refresh_from_db()
    t_none.refresh_from_db()

    assert t_connected.charges_enabled is True, (
        "Tenant with connected account must be charge-ready after backfill"
    )
    assert t_none.charges_enabled is False, (
        "Tenant without connected account must remain non-charge-ready"
    )
