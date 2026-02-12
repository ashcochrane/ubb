from typing import Protocol


class PaymentConnector(Protocol):
    """Interface that any payment connector must implement.

    Connectors subscribe to billing outbox events and handle
    payment collection. They call billing's credit/debit
    internally to update the ledger.
    """

    def handle_topup_requested(
        self, tenant_id: str, customer_id: str, amount_micros: int,
        trigger: str, success_url: str, cancel_url: str,
    ) -> dict | None:
        """Called when a customer needs to top up.
        Returns checkout URL or None if handled async."""
        ...

    def handle_balance_low(
        self, tenant_id: str, customer_id: str, balance_micros: int,
        suggested_topup_micros: int,
    ) -> None:
        """Called when balance drops below auto-topup threshold.
        Connector should initiate auto-charge if possible."""
        ...
