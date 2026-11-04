"""Re-run one recorded Stripe webhook event that failed retryably, now.

R10 Stage C4 (PLAN §7 item 36, the recovery ruling). An event whose handler
failed retryably — a subscription invoice that arrived before its mirror was
bound is the case this exists for — is recovered on the SAME durable record
by either of two routes: Stripe's own redelivery, or this command. Until C4
this command only reset the row to ``processing``. That refreshed the row,
so the receiver's CAS answered every redelivery ``already_processing`` for
the next ``PROCESSING_TTL_MINUTES``, and nothing ran the event at all.

What it does now, all on the one receiver-scoped ``StripeWebhookEvent`` row:

1. finds that row, and refuses unless it is ``failed`` and retryable;
2. retrieves the authoritative Event from Stripe, by the stored event id,
   through ``stripe_call`` under the ``--tenant``'s key and connected account
   (a missing key is refused before any request);
3. refuses unless the Event's id, type, connected account and livemode all
   agree with the row and the tenant;
4. runs it through the receiver core, ``process_stripe_event``: the same CAS
   that arbitrates deliveries claims the row, the receiver's own handler map
   dispatches it, and the row records the result as a delivery's would.

It writes no other record and stores no payload. Stripe keeps an Event for
30 days; one older than that cannot be retrieved, and only a redelivery
within Stripe's own retry window could recover it.
"""
import uuid

import stripe
from django.core.management.base import BaseCommand, CommandError
from django.urls import get_resolver

from apps.billing.stripe.models import WEBHOOK_RECEIVERS, StripeWebhookEvent
from apps.billing.stripe.receiver import (
    OUTCOME_ALREADY_PROCESSED,
    OUTCOME_ALREADY_PROCESSING,
    OUTCOME_FAILED,
    OUTCOME_FAILED_RETRYABLE,
    OUTCOME_SUCCEEDED,
    process_stripe_event,
    registered_receiver,
)
from apps.billing.stripe.services.stripe_service import api_key_for_tenant, field, stripe_call
from apps.platform.tenants.models import Tenant
from core.exceptions import StripeFatalError, StripeNotConfigured, StripeTransientError


def _load_the_deployments_endpoints():
    """Import the endpoint modules this deployment mounts, so each has
    registered its receiver with the receiver core.

    The receivers a deployment serves are the endpoints its URLconf mounts,
    and each endpoint module registers its handler map as it loads
    (ADR-001 decision 5, the receiver registry). Resolving the URL patterns
    imports the URLconf and everything it mounts, exactly as
    ``manage.py check`` does, so this billing module reaches the billing
    handler map without importing the composition layer.
    """
    return get_resolver().url_patterns


class Command(BaseCommand):
    help = (
        "Re-run one webhook event that failed retryably, now: retrieve it from "
        "Stripe under the tenant's key and connected account, then process it "
        "through the receiver on its own recorded row. Deduplication is per "
        "receiver (C1b, F-17), so the receiver that recorded the failure is "
        "named: --receiver billing | subscriptions."
    )

    def add_arguments(self, parser):
        parser.add_argument("stripe_event_id", type=str)
        # The closed set is the model's (`WEBHOOK_RECEIVERS`), checked below
        # rather than restated as an argparse `choices=` — one declared value
        # set, where the row lands.
        parser.add_argument(
            "--receiver", required=True,
            help="the receiver whose row to re-run, one of "
                 f"{', '.join(sorted(WEBHOOK_RECEIVERS))} (each receiver keeps its own)")
        parser.add_argument(
            "--tenant", required=True,
            help="the id of the tenant whose connected account the event came from; "
                 "its mode picks the Stripe key, and no key is ever an argument")

    def handle(self, *args, **options):
        event_id = options["stripe_event_id"]
        receiver = options["receiver"]
        if receiver not in WEBHOOK_RECEIVERS:
            raise CommandError(
                f"unknown receiver {receiver!r}; one of {', '.join(sorted(WEBHOOK_RECEIVERS))}")
        try:
            row = StripeWebhookEvent.objects.get(receiver=receiver, stripe_event_id=event_id)
        except StripeWebhookEvent.DoesNotExist:
            raise CommandError(
                f"No webhook event found with stripe_event_id={event_id} "
                f"on the {receiver} receiver")

        if row.status != "failed":
            raise CommandError(
                f"Event is '{row.status}', not 'failed'. "
                "Only failed events can be reprocessed."
            )
        if not (row.failure_reason and row.failure_reason.get("retryable") is True):
            raise CommandError(
                f"Event {event_id} failed NON-retryably on the {receiver} receiver "
                f"({(row.failure_reason or {}).get('type', 'unknown')}). The receiver "
                "never runs such an event again, and neither does this command.")

        tenant = self._tenant(options["tenant"])
        connected = tenant.stripe_connected_account_id
        if not connected:
            raise CommandError(
                f"tenant {tenant.id} has no connected Stripe account to retrieve "
                f"{event_id} from; nothing was requested")
        livemode = not tenant.is_sandbox

        dispatch = self._dispatch(receiver)
        handlers, refuses_without_a_wallet_subject = dispatch
        if row.event_type not in handlers:
            raise CommandError(
                f"the {receiver} receiver does not handle {row.event_type!r}; "
                "nothing was requested")

        event = self._retrieve(tenant, connected, event_id)
        self._agree(event, row, connected, livemode)

        outcome = process_stripe_event(
            event, receiver=receiver, handlers=handlers,
            refuses_without_a_wallet_subject=refuses_without_a_wallet_subject)
        row.refresh_from_db()
        if outcome == OUTCOME_SUCCEEDED:
            self.stdout.write(self.style.SUCCESS(
                f"Event {event_id} on the {receiver} receiver was reprocessed: succeeded."))
            return
        if outcome == OUTCOME_ALREADY_PROCESSED and row.status == "succeeded":
            self.stdout.write(
                f"Event {event_id} on the {receiver} receiver was already processed "
                "by a Stripe delivery; nothing was run again.")
            return
        if outcome in (OUTCOME_ALREADY_PROCESSED, OUTCOME_ALREADY_PROCESSING):
            raise CommandError(
                f"Event {event_id} was claimed by a concurrent delivery (its row is "
                f"'{row.status}'); nothing was run here. Check its row again shortly.")
        if outcome == OUTCOME_FAILED_RETRYABLE:
            raise CommandError(
                f"Event {event_id} was reprocessed and failed again, retryably: "
                f"{row.failure_reason}. Its row stays failed and retryable.")
        if outcome == OUTCOME_FAILED:
            raise CommandError(
                f"Event {event_id} was reprocessed and failed non-retryably: "
                f"{row.failure_reason}.")
        raise CommandError(f"Event {event_id} was not processed: {outcome}.")

    @staticmethod
    def _tenant(value):
        try:
            tenant_id = uuid.UUID(str(value))
        except ValueError:
            raise CommandError(f"--tenant {value!r} is not a tenant id")
        tenant = Tenant.objects.filter(id=tenant_id).first()
        if tenant is None:
            raise CommandError(f"no tenant {tenant_id}")
        return tenant

    @staticmethod
    def _dispatch(receiver):
        _load_the_deployments_endpoints()
        dispatch = registered_receiver(receiver)
        if dispatch is None:
            raise CommandError(
                f"no handler map is registered for the {receiver} receiver in this "
                "deployment; nothing was requested")
        return dispatch

    @staticmethod
    def _retrieve(tenant, connected, event_id):
        """The Event Stripe holds under ``event_id``, on the tenant's connected
        account, through the guarded transport. Nothing is invented on a
        refusal: the row is left exactly as it was, failed and retryable."""
        try:
            return stripe_call(
                stripe.Event.retrieve, api_key=api_key_for_tenant(tenant),
                id=event_id, stripe_account=connected)
        except StripeNotConfigured as e:
            raise CommandError(
                f"refused before any request to Stripe: {e} The row is unchanged.")
        except (StripeFatalError, StripeTransientError) as e:
            raise CommandError(
                f"Stripe did not return event {event_id} on {connected}: {e}. "
                "Nothing was processed and the row is unchanged (failed, retryable).")

    @staticmethod
    def _agree(event, row, connected, livemode):
        """Refuse an Event whose facts disagree with the row or the tenant."""
        facts = {
            "id": (field(event, "id"), row.stripe_event_id),
            "type": (field(event, "type"), row.event_type),
            "account": (field(event, "account"), connected),
            "livemode": (bool(field(event, "livemode", False)), livemode),
        }
        disagree = {name: got for name, (got, want) in facts.items() if got != want}
        if disagree:
            raise CommandError(
                f"the retrieved event disagrees with the recorded row and the "
                f"tenant on {', '.join(sorted(disagree))} "
                f"({', '.join(f'{k}={v!r}' for k, v in sorted(disagree.items()))}); "
                "nothing was processed and the row is unchanged")
