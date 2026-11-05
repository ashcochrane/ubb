"""``set_customer_manual_hold`` — the operator surface for the manual hold (R10
Stage C4; owner/consultant ruling 2026-11-05, PLAN §7 item 41, FINAL).

    manage.py set_customer_manual_hold --customer <uuid> --state held|released \\
        --operator <operator id>

``held`` places a manual hold on an active, live customer; ``released`` lifts
that hold. Both refuse a customer suspended for a system cause — a hold never
overwrites, and a release never clears, a cause its own recovery owns. The
rules and the side effects are the service's
(``apps/billing/gating/services/manual_hold.py``); this command only parses,
asks and reports. The Django Customer admin no longer edits ``status``,
``suspension_reason`` or ``deleted_at``: this is the one supported way to hold
or release a customer.
"""
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.billing.gating.services import manual_hold

STATES = ("held", "released")


class Command(BaseCommand):
    help = (
        "Place (held) or release (released) an accountable operator's manual hold "
        "on one customer. Refuses a customer suspended for a system cause."
    )

    def add_arguments(self, parser):
        parser.add_argument("--customer", required=True, help="The customer's id.")
        parser.add_argument("--state", required=True, choices=STATES,
                            help="held places the hold; released lifts it.")
        parser.add_argument("--operator", required=True,
                            help="The acting UBB operator's id, kept on every outcome.")

    def handle(self, *args, **options):
        operator = (options["operator"] or "").strip()
        if not operator:
            raise CommandError("--operator must name the accountable operator")
        try:
            customer_id = uuid.UUID(str(options["customer"]))
        except ValueError:
            raise CommandError(f"--customer {options['customer']!r} is not a customer id")
        act = (manual_hold.place_manual_hold if options["state"] == "held"
               else manual_hold.release_manual_hold)
        try:
            outcome = act(customer_id, operator=operator)
        except manual_hold.ManualHoldRefused as e:
            raise CommandError(f"refused: {e}. Nothing was written.")
        except manual_hold.ManualHoldFailed as e:
            raise CommandError(f"failed: {e}. Nothing was written.")
        messages = {
            manual_hold.HELD: f"Customer {customer_id} is now under a manual hold.",
            manual_hold.ALREADY_HELD: f"Customer {customer_id} was already under a "
                                      "manual hold; nothing changed.",
            manual_hold.RELEASED: f"Customer {customer_id}'s manual hold is released.",
            manual_hold.ALREADY_ACTIVE: f"Customer {customer_id} is already active; "
                                        "nothing changed.",
            manual_hold.HANDED_OVER: f"Customer {customer_id}'s manual hold is lifted, "
                                     "but a standing payment failure keeps it suspended "
                                     "for payment_failed, which its own recovery owns.",
        }
        style = (self.style.WARNING if outcome == manual_hold.HANDED_OVER
                 else self.style.SUCCESS)
        self.stdout.write(style(messages[outcome]))
