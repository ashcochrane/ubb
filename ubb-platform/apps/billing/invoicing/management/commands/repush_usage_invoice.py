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

        if rec.status not in ("failed", "failed_permanent", "skipped"):
            # 'pending'/'pushing' rows are already owned by the hourly reconcile;
            # resetting a 'pushed' row would re-record an already-billed invoice.
            raise CommandError(
                f"Row {rec.id} has status '{rec.status}' — repush only applies to "
                "'failed', 'failed_permanent' or 'skipped' rows. Pending/pushing rows "
                "are retried automatically; a pushed row is already billed."
            )

        owner = rec.customer.resolve_billing_owner()
        if owner.id != rec.customer_id:
            # The owner-first service re-keys every push on the billing owner, so a
            # seat-keyed row would loop 'pending' forever without ever transitioning.
            raise CommandError(
                f"Row {rec.id} is keyed on pooled seat '{rec.customer.external_id}' "
                f"(billing owner '{owner.external_id}'). The owner-first push can never "
                "transition it — repush the owner-keyed row for this period instead."
            )

        if options["rebill_void"] and rec.invoice_kind == "consolidated":
            # F5.5 Fix 3: a consolidated target is the customer's subscription
            # renewal — a Stripe-owned draft that auto-finalizes on Stripe's
            # clock.  Voiding it in Stripe and re-routing usage to a new
            # renewal is not the same operation as voiding a standalone invoice,
            # and the --rebill-void machinery (clear pointer + bump generation)
            # would only re-resolve a NEW renewal draft on the next push — it
            # does NOT void the old one.  Refuse with a clear message so the
            # operator understands what to do instead.
            raise CommandError(
                f"Row {rec.id} has invoice_kind='consolidated' — a consolidated "
                "target is the customer's subscription renewal invoice and cannot "
                "be replaced via --rebill-void (that flag is for standalone usage "
                "invoices you have already voided in Stripe). Use a plain repush "
                "to resume the existing renewal, or handle the renewal directly "
                "in Stripe and then plain-repush to record the outcome."
            )

        was_migrated_legacy = rec.last_attempt_error.startswith("migrated:")
        # Deploy-window belt: a row attempted without a recorded pointer may still
        # have an unfindable (pre-metadata) Stripe invoice — same manual check.
        attempted_without_pointer = rec.push_attempts > 0 and not rec.stripe_invoice_id

        # F1.1: carry_in_micros is deliberately untouched in EVERY mode — a
        # resumed push reuses the pinned reservation, and a --rebill-void
        # re-bills the same carry (the voided invoice never collected it).
        rec.push_attempts = 0
        rec.first_attempted_at = None
        rec.last_attempt_error = ""
        rec.status = "pending"
        rec.skip_reason = ""
        update_fields = ["push_attempts", "first_attempted_at", "last_attempt_error",
                         "status", "skip_reason", "updated_at"]
        if options["rebill_void"]:
            # A rebill is a FRESH billing decision: drop the frozen line snapshot
            # so the new push re-aggregates, and bump the generation so every
            # idempotency-key family rotates — a key replay inside Stripe's 24h
            # window would otherwise return the recorded (now-void) invoice and
            # Phase 3 would record 'pushed' against it without rebilling.
            rec.stripe_invoice_id = ""
            rec.push_phase = ""
            rec.line_snapshot = []
            rec.rebill_generation += 1
            update_fields += ["stripe_invoice_id", "push_phase",
                              "line_snapshot", "rebill_generation"]
        rec.save(update_fields=update_fields)

        if (was_migrated_legacy or attempted_without_pointer) and not rec.stripe_invoice_id:
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
