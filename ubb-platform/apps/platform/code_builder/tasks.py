"""Removing the snapshots nobody has resolved for a while (#580).

A snapshot is a derived fixture, and the period it is kept is
`snapshots.RETENTION`. A pruned fingerprint answers not-found. Resolving the
selection again brings the same fingerprint back only if the configuration
still resolves to exactly the same content; otherwise the generated file that
carries it can no longer be verified and is generated again
(`snapshots.py`, "What a prune costs").
"""
import logging

from celery import shared_task

from apps.platform.code_builder import snapshots

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_events")
def prune_blueprint_snapshots():
    """Delete every snapshot past its retention period, for every tenant.
    Returns how many went."""
    pruned = snapshots.prune()
    if pruned:
        logger.info("code_builder.snapshots_pruned",
                    extra={"data": {"pruned": pruned}})
    return pruned
