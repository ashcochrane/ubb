"""``set_customer_manual_hold`` — the operator surface for the manual hold (R10
Stage C4; owner/consultant ruling 2026-11-05, PLAN §7 item 41, FINAL).

    manage.py set_customer_manual_hold --customer <uuid> --state held|released \\
        --operator <operator id>

``held`` places a manual hold on an active, live customer; ``released`` removes
that hold — the MANUAL cause only: if a system condition still stands (a
payment failure, a stop line still open under ``enforcing``, a wallet past its
floor) the customer stays suspended for it, and the command says so; it never
forces a customer active. Both refuse a customer suspended for a system cause
— a hold never overwrites, and a release never clears, a cause its own
recovery owns. The rules and the side effects are the service's
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
        ok, warn = self.style.SUCCESS, self.style.WARNING
        report = {
            manual_hold.HELD: (ok, f"Customer {customer_id} is now under a manual hold."),
            manual_hold.ALREADY_HELD: (ok, f"Customer {customer_id} was already under a "
                                           "manual hold; nothing changed."),
            manual_hold.RELEASED: (ok, f"Customer {customer_id}'s manual hold is released; "
                                       "it is active again."),
            manual_hold.ALREADY_ACTIVE: (ok, f"Customer {customer_id} is already active; "
                                             "nothing changed."),
            # The hold IS released — not a failure — but a system cause still
            # stands, so the customer is not active: say which.
            manual_hold.HANDED_OVER: (warn, f"Customer {customer_id}'s manual hold is "
                                            "released, but it remains suspended for "
                                            f"{outcome.cause!r}, a system cause its own "
                                            "recovery lifts."),
        }
        style, message = report[outcome]
        self.stdout.write(style(message))
