"""What a publication sets going once it has committed (#568; the consultant's
review of #618).

A publication commits the declaration alone. The held names its key answers
are registered and replayed here, afterwards, one at a time
(`quarantine.answer_what_publications_declare`) — so the publication's
transaction does not grow with the history held under the key, and one held
event that cannot be answered leaves the declaration published. A Resolution
Run answers the same names whenever it runs, which is the retry if this never
does.
"""
import logging

from celery import shared_task

from apps.platform.event_types.quarantine import (
    answer_what_publications_declare)

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_events")
def answer_held_names(tenant_id, key):
    """Answer the held names a publication at ``key`` now answers, for
    ``tenant_id``. Returns how many were registered and how many stay held."""
    answered = answer_what_publications_declare(tenant_id=tenant_id, key=key)
    if answered.registered or answered.still_held:
        logger.info("quarantine.held_names_answered",
                    extra={"data": {"tenant_id": tenant_id, "key": key,
                                    "registered": answered.registered,
                                    "still_held": answered.still_held}})
    return tuple(answered)
