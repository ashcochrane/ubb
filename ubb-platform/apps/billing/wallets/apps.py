from django.apps import AppConfig


class WalletsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.wallets"
    label = "wallets"

    def ready(self):
        from apps.platform.work.hooks import register_terminal_transition_listener
        from apps.billing.wallets.reservations import release_on_terminal_transition

        # The kernel owns the terminal-transition seam and never imports a
        # product (ADR-001 rule 2; the platform-hooks channel of rule 3, the
        # fourth in CLAUDE.md's list): every terminal transition of a unit of
        # work notifies this listener, which releases the prepaid reservation
        # the unit's start took (#461, slice 6 §5) — synchronously, inside
        # the transition's own transaction, under a savepoint the registry
        # holds so a failure here can veto nothing.
        register_terminal_transition_listener(release_on_terminal_transition)
