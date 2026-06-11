from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.billing.invoicing.models import CustomerUsageInvoice


class Command(BaseCommand):
    help = (
        "Reset a usage-invoice push for another bounded retry: zero the attempt "
        "counters and flip the row back to 'pending' so the hourly reconcile "
        "resumes it (retrieve-first, never recreate)."
    )

    def add_arguments(self, parser):
        parser.add_argument("row_id", type=str, help="CustomerUsageInvoice id")
        parser.add_argument(
            "--rebill-void", action="store_true",
            help="Clear stripe_invoice_id/push_phase so a deliberately-voided "
                 "Stripe invoice is replaced (the pre-create lookup skips void "
                 "invoices, so the next push mints a fresh one).",
        )

    def handle(self, *args, **options):
        try:
            rec = CustomerUsageInvoice.objects.get(id=options["row_id"])
        except (CustomerUsageInvoice.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"No CustomerUsageInvoice found with id={options['row_id']}")

        owner = rec.customer.resolve_billing_owner()
        if owner.id != rec.customer_id:
            # The owner-first service re-keys every push on the billing owner, so a
            # seat-keyed row would loop 'pending' forever without ever transitioning.
            raise CommandError(
                f"Row {rec.id} is keyed on pooled seat '{rec.customer.external_id}' "
                f"(billing owner '{owner.external_id}'). The owner-first push can never "
                "transition it — repush the owner-keyed row for this period instead."
            )

        was_migrated_legacy = rec.last_attempt_error.startswith("migrated:")

        rec.push_attempts = 0
        rec.first_attempted_at = None
        rec.last_attempt_error = ""
        rec.status = "pending"
        rec.skip_reason = ""
        update_fields = ["push_attempts", "first_attempted_at", "last_attempt_error",
                         "status", "skip_reason", "updated_at"]
        if options["rebill_void"]:
            rec.stripe_invoice_id = ""
            rec.push_phase = ""
            update_fields += ["stripe_invoice_id", "push_phase"]
        rec.save(update_fields=update_fields)

        if was_migrated_legacy and not rec.stripe_invoice_id:
            self.stdout.write(self.style.WARNING(
                "This row predates invoice metadata: duplicate protection only covers "
                "invoices created post-F0.1. Before repushing you MUST search Stripe by "
                "customer + period + amount and, if an invoice exists, record its id on "
                "stripe_invoice_id so the push resumes it instead of minting a duplicate."
            ))
        self.stdout.write(self.style.SUCCESS(
            f"Row {rec.id} reset to 'pending'"
            + (" (stripe_invoice_id/push_phase cleared for void rebill)"
               if options["rebill_void"] else "")
            + ". The hourly reconcile_postpaid_usage task will pick it up."
        ))
