from django.core.management.base import BaseCommand, CommandError

from apps.billing.stripe.models import WEBHOOK_RECEIVERS, StripeWebhookEvent


class Command(BaseCommand):
    help = (
        "Reset a failed webhook event to 'processing' for manual reprocessing. "
        "Deduplication is per receiver (C1b, F-17), so the receiver that recorded "
        "the failure is named: --receiver billing | subscriptions."
    )

    def add_arguments(self, parser):
        parser.add_argument("stripe_event_id", type=str)
        # The closed set is the model's (`WEBHOOK_RECEIVERS`), checked below
        # rather than restated as an argparse `choices=` — one declared value
        # set, where the row lands.
        parser.add_argument(
            "--receiver", required=True,
            help="the receiver whose row to reset, one of "
                 f"{', '.join(sorted(WEBHOOK_RECEIVERS))} (each receiver keeps its own)")

    def handle(self, *args, **options):
        event_id = options["stripe_event_id"]
        receiver = options["receiver"]
        if receiver not in WEBHOOK_RECEIVERS:
            raise CommandError(
                f"unknown receiver {receiver!r}; one of {', '.join(sorted(WEBHOOK_RECEIVERS))}")
        try:
            event = StripeWebhookEvent.objects.get(
                receiver=receiver, stripe_event_id=event_id)
        except StripeWebhookEvent.DoesNotExist:
            raise CommandError(
                f"No webhook event found with stripe_event_id={event_id} "
                f"on the {receiver} receiver")

        if event.status != "failed":
            raise CommandError(
                f"Event is '{event.status}', not 'failed'. "
                "Only failed events can be reprocessed."
            )

        event.status = "processing"
        event.failure_reason = None
        event.save(update_fields=["status", "failure_reason", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Event {event_id} on the {receiver} receiver reset to 'processing'. "
                "Re-deliver the webhook from Stripe Dashboard to that receiver's endpoint."
            )
        )
