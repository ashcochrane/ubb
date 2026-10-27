"""
Billing-specific lock helpers.

See core/locking.py for canonical lock ordering:
    Run -> Wallet -> Customer -> TopUpAttempt -> Invoice -> Posting

These helpers enforce the ordering for billing operations.

Note: Run and Wallet locks are never co-held today; Run is listed first in the
canonical order to reserve the position if that ever changes.
"""
from core.locking import lock_row


def currency_a_wallet_is_born_in(owner):
    """The one rule for a wallet's currency at birth: its owner's tenant's,
    which UBB v1 holds to US dollars (ADR-0023) — never a literal.

    Named so the outbound rail can ask what a not-yet-born wallet WILL hold
    without a second copy of the rule (#565).
    """
    return owner.tenant.default_currency


def the_currency_a_top_up_credits(attempt):
    """``(record, currency)``: the wallet a top-up attempt credits, and its
    currency — the authoritative monetary object every top-up call to the
    rail draws its currency from (#565).

    The billing owner PINNED on the attempt, whose wallet the credit lands
    on. Where that wallet has not been born yet (a first top-up), the record
    is the rule that will bear it, so the call and the credit cannot read
    two different answers. An attempt pinned before the owner was (a row no
    creation path writes any more) reads its seat's owner: this moves no
    money, it only names a currency.
    """
    from apps.billing.wallets.models import Wallet
    from apps.platform.customers.models import Customer

    owner_id = (attempt.billing_owner_id
                or attempt.customer.resolve_billing_owner().id)
    wallet = Wallet.objects.filter(customer_id=owner_id).first()
    if wallet is not None:
        return f"wallet {wallet.id}", wallet.currency
    owner = Customer.objects.select_related("tenant").get(id=owner_id)
    return (f"the wallet customer {owner_id} will be born with",
            currency_a_wallet_is_born_in(owner))


def lock_for_billing(customer_id):
    """
    Acquire Wallet -> Customer locks in canonical order.
    Creates the Wallet lazily if it doesn't exist yet.

    Use for: usage recording, wallet credits/debits, suspension checks.
    MUST be called within @transaction.atomic.

    Task 8c ratchet: refuses an id that is not itself a billing owner.
    Seven instances of the same defect (Tasks 3, 7, 8) were all one shape —
    a caller reached this function with a pooled seat's id, and the lazy
    ``Wallet.objects.create`` below turned that into a silent phantom wallet
    on the seat instead of a loud failure. Every legitimate caller in this
    codebase already resolves the owner first (``customer.resolve_billing_
    owner()``); this assertion makes skipping that step a hard error at the
    first test run rather than a wallet nothing ever reads.

    The two things that legitimately key off a SEAT rather than the owner —
    ``CustomerSpendPool`` (a pool bounds the seat's own spend) and audit records
    (the seat is the named subject of an action) — never call this function;
    they read/write their own tables directly. If that ever changes, they
    would need to be added to a deliberate allowlist, not silently pass here.
    """
    from apps.billing.wallets.models import Wallet
    from apps.platform.customers.models import Customer
    from core.exceptions import NotBillingOwnerError

    # Plain (unlocked) read, purely to validate identity — it does not
    # participate in the Wallet -> Customer lock order below.
    customer_for_check = Customer.objects.select_related("parent", "tenant").get(id=customer_id)
    owner = customer_for_check.resolve_billing_owner()
    if owner.id != customer_for_check.id:
        raise NotBillingOwnerError(
            f"lock_for_billing() called with seat {customer_id} "
            f"(external_id={customer_for_check.external_id!r}) — its billing "
            f"owner is {owner.id} (external_id={owner.external_id!r}). "
            "Resolve customer.resolve_billing_owner() before calling in.")

    wallet = Wallet.all_objects.select_for_update().filter(customer_id=customer_id).first()
    if wallet is None:
        wallet = Wallet.objects.create(
            customer_id=customer_id, balance_micros=0,
            currency=currency_a_wallet_is_born_in(customer_for_check))
    elif wallet.deleted_at is not None:
        wallet.restore()
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer


def lock_top_up_attempt(attempt_id):
    """
    Acquire TopUpAttempt lock.

    Use for: status transitions after Stripe calls.
    MUST be called within @transaction.atomic.
    """
    from apps.billing.topups.models import TopUpAttempt
    return TopUpAttempt.objects.select_for_update().get(id=attempt_id)


def lock_invoice(invoice_id):
    """
    Acquire Invoice lock.

    Use for: status transitions from webhooks.
    MUST be called within @transaction.atomic.
    """
    from apps.billing.invoicing.models import Invoice
    return Invoice.objects.select_for_update().get(id=invoice_id)
