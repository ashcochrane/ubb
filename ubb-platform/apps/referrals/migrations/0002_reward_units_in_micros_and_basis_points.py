"""A referral reward's figure carries its unit (R10 Stage C5, A-3, RULED Q9).

One Decimal column, ``reward_value``, meant micros for a flat fee and a
FRACTION for a share; ``estimated_cost_percentage`` was a fraction capped at
9.9999 while the API admitted 0..100 — and the console sent "10 %" as ``10``,
which the backend multiplied by as a fraction. Each figure now has exactly one
explicit integer unit: a flat fee is ``reward_amount_micros``, a share is
``reward_share_basis_points`` (1..10000), the fallback cost estimate is
``estimated_cost_basis_points`` (0..10000); the referral's snapshots follow.

The Decimal columns are DROPPED, not renamed — a unit change, not a new name
for the same value — and NO data step carries rows across (the ruled shape,
PLAN §5.5 A-3: "migration adds the integer columns and drops the Decimal ones
— no production data"). Two reasons, both stated here as ADR-0007 §1 asks:
there is no row to carry — UBB is deployed nowhere and the cutover's fresh
database holds no referral programme — and UBB's migrations admit no Python
data step at all since the cutover (ADR-0026 §6's structural half,
``api/v1/tests/test_the_audit_catalogue_is_the_registrys.py``: a ``RunPython``
"can do anything", so none may exist). The conversion a data step WOULD make
is determinate — the reward type says which unit the old Decimal meant — and
is recorded in the SDK's MIGRATION.md §27 for any integrator holding values
of their own; it is not run here because there is nothing for it to run on.
"""
from django.db import migrations, models

#: ADR-0007 §1: every drop states its reason.
DROPS = {
    "referralprogram.reward_value": (
        "replaced by two explicit-unit integer columns, reward_amount_micros "
        "(flat fee) and reward_share_basis_points (share); the one Decimal "
        "meant micros or a fraction by reward type; no production row exists "
        "(pre-launch), and no Python data step is admitted (ADR-0026 §6)"),
    "referralprogram.estimated_cost_percentage": (
        "replaced by estimated_cost_basis_points (0..10000); the Decimal was a "
        "fraction capped at 9.9999 behind an API admitting 0..100; no "
        "production row exists (pre-launch)"),
    "referral.snapshot_reward_value": (
        "replaced by snapshot_reward_amount_micros and "
        "snapshot_reward_share_basis_points, the programme's figures in their "
        "explicit unit each, as copied at attribution; no production row "
        "exists (pre-launch)"),
    "referral.snapshot_estimated_cost_percentage": (
        "replaced by snapshot_estimated_cost_basis_points; no production row "
        "exists (pre-launch)"),
}

#: ADR-0007 §1: a drop beside an add on the same model is not a rename — the
#: new columns hold a different unit (and, for the reward, two columns for
#: one), so RenameField would have carried a value under the wrong unit.
NOT_A_RENAME = {
    "referralprogram.reward_value": (
        "a unit change, not a rename: micros-or-fraction split into micros "
        "and basis points"),
    "referralprogram.estimated_cost_percentage": (
        "a unit change, not a rename: a fraction becomes basis points"),
    "referral.snapshot_reward_value": (
        "a unit change, not a rename: micros-or-fraction split into micros "
        "and basis points"),
    "referral.snapshot_estimated_cost_percentage": (
        "a unit change, not a rename: a fraction becomes basis points"),
}


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralprogram",
            name="reward_amount_micros",
            field=models.BigIntegerField(
                blank=True, null=True,
                help_text="The flat fee, in micros, paid once per referral (flat_fee only)"),
        ),
        migrations.AddField(
            model_name="referralprogram",
            name="reward_share_basis_points",
            field=models.IntegerField(
                blank=True, null=True,
                help_text="The share of revenue or profit, in basis points 1..10000 "
                          "(revenue_share / profit_share only)"),
        ),
        migrations.AddField(
            model_name="referralprogram",
            name="estimated_cost_basis_points",
            field=models.IntegerField(
                blank=True, null=True,
                help_text="Fallback for profit-share: the tenant's cost as a share of "
                          "revenue, in basis points 0..10000"),
        ),
        migrations.RemoveField(
            model_name="referralprogram",
            name="reward_value",
        ),
        migrations.RemoveField(
            model_name="referralprogram",
            name="estimated_cost_percentage",
        ),
        migrations.AddField(
            model_name="referral",
            name="snapshot_reward_amount_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="referral",
            name="snapshot_reward_share_basis_points",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="referral",
            name="snapshot_estimated_cost_basis_points",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.RemoveField(
            model_name="referral",
            name="snapshot_reward_value",
        ),
        migrations.RemoveField(
            model_name="referral",
            name="snapshot_estimated_cost_percentage",
        ),
    ]
