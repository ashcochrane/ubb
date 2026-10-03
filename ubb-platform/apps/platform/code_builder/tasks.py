"""Removing the snapshots nobody has resolved for a while (#580).

A snapshot is a derived fixture, and the period it is kept is
`snapshots.RETENTION`. Pruning one costs a developer little: resolving the
same selection over the same configuration stores the same content under the
same fingerprint, so a pruned fingerprint answers not-found until somebody
resolves again, and then answers as it did.
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
