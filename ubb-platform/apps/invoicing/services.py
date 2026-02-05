import logging
from django.utils import timezone
from apps.metering.usage.models import Invoice
from apps.stripe_integration.services.stripe_service import stripe_call, micros_to_cents

logger = logging.getLogger(__name__)


class ReceiptService:
    @staticmethod
    def create_topup_receipt(customer, top_up_attempt):
        """Create a paid receipt invoice for a completed top-up.

        Only creates local Invoice record if ALL Stripe calls succeed.
        On Stripe failure, no local record is created — the next webhook
        retry or manual trigger can retry from scratch.
        """
        # Idempotency: skip if invoice already exists
        if Invoice.objects.filter(top_up_attempt=top_up_attempt).exists():
            return

        import stripe

        connected_account = customer.tenant.stripe_connected_account_id
        amount_cents = micros_to_cents(top_up_attempt.amount_micros)

        try:
            stripe_invoice = stripe_call(
                stripe.Invoice.create,
                retryable=True,
                idempotency_key=f"receipt-{top_up_attempt.id}",
                customer=customer.stripe_customer_id,
                auto_advance=False,
                collection_method="send_invoice",
                days_until_due=0,
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.InvoiceItem.create,
                retryable=True,
                idempotency_key=f"receipt-item-{top_up_attempt.id}",
                customer=customer.stripe_customer_id,
                invoice=stripe_invoice.id,
                amount=amount_cents,
                currency="usd",
                description="Account Top-Up",
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.Invoice.finalize_invoice,
                retryable=True,
                idempotency_key=f"receipt-finalize-{top_up_attempt.id}",
                invoice=stripe_invoice.id,
                stripe_account=connected_account,
            )

            stripe_call(
                stripe.Invoice.pay,
                retryable=True,
                idempotency_key=f"receipt-pay-{top_up_attempt.id}",
                invoice=stripe_invoice.id,
                paid_out_of_band=True,
                stripe_account=connected_account,
            )
        except Exception:
            logger.exception(
                "Failed to create Stripe receipt invoice — no local record created, retryable",
                extra={"data": {"attempt_id": str(top_up_attempt.id)}},
            )
            return  # No local record — allows retry

        Invoice.objects.create(
            tenant=customer.tenant,
            customer=customer,
            top_up_attempt=top_up_attempt,
            stripe_invoice_id=stripe_invoice.id,
            total_amount_micros=top_up_attempt.amount_micros,
            status="paid",
            finalized_at=timezone.now(),
            paid_at=timezone.now(),
        )
