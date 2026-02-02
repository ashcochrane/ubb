from django.core.management.base import BaseCommand, CommandError

from apps.stripe_integration.models import StripeWebhookEvent


class Command(BaseCommand):
    help = "Reset a failed webhook event to 'processing' for manual reprocessing"

    def add_arguments(self, parser):
        parser.add_argument("stripe_event_id", type=str)

    def handle(self, *args, **options):
        event_id = options["stripe_event_id"]
        try:
            event = StripeWebhookEvent.objects.get(stripe_event_id=event_id)
        except StripeWebhookEvent.DoesNotExist:
            raise CommandError(f"No webhook event found with stripe_event_id={event_id}")

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
                f"Event {event_id} reset to 'processing'. "
                "Re-deliver the webhook from Stripe Dashboard."
            )
        )
