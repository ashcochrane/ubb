# UBB Architecture: Two-Product Separation

## Overview

UBB can be split into two independent products that work together but can also integrate with third-party alternatives:

1. **Usage Metering** - Tracks consumption, manages balances, calculates costs
2. **Billing & Payments** - Handles money movement, payment methods, invoicing

This document explains how these systems work independently and together.

---

## The Two Products

### Product 1: Usage Metering

**What it does:** Tracks how much customers use and what they owe.

**Owns:**
- Usage events (what happened, when, how much it cost)
- Wallets (customer balances)
- Transactions (the ledger of all balance changes)
- Pricing rules (how to calculate costs)
- Thresholds (when to trigger alerts)

**Knows nothing about:**
- How payments are collected
- What payment provider is used
- Credit cards, bank accounts, or invoices

**Analogy:** Think of it as a utility meter. It measures consumption and tracks what you owe. It doesn't care if you pay by card, cash, or check.

---

### Product 2: Billing & Payments

**What it does:** Collects money and manages payment relationships.

**Owns:**
- Payment methods (cards, bank accounts)
- Top-up attempts (pending, succeeded, failed charges)
- Invoices and receipts
- Payment provider integration (Stripe, etc.)

**Knows nothing about:**
- What the customer is using the balance for
- How costs are calculated
- Usage events or metrics

**Analogy:** Think of it as a payment terminal. It knows how to charge cards and track payments. It doesn't care what you're paying for.

---

## How They Communicate

The two systems talk through a simple contract: **events** and **commands**.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                        THE CONTRACT                                 │
│                                                                     │
│   USAGE METERING                           BILLING & PAYMENTS       │
│                                                                     │
│   Emits Events:                            Emits Commands:          │
│   ─────────────                            ───────────────          │
│   • balance.low                            • credit_wallet          │
│   • balance.depleted                       • debit_wallet           │
│   • customer.suspended                                              │
│                                                                     │
│   Accepts Commands:                        Accepts Events:          │
│   ────────────────                         ──────────────           │
│   • credit_wallet                          • balance.low            │
│   • debit_wallet                           • balance.depleted       │
│   • get_balance                            • customer.suspended     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Key principle:** Neither system stores the other's data. Usage doesn't know about payment methods. Billing doesn't track balances.

---

## The Flows

### Flow 1: Recording Usage

This is the core operation - a customer uses something, we record it and deduct from their balance.

```
Customer uses API
        │
        ▼
┌───────────────────┐
│  USAGE METERING   │
│                   │
│  1. Validate the  │
│     request       │
│                   │
│  2. Calculate     │
│     the cost      │
│                   │
│  3. Check if      │
│     balance is    │
│     sufficient    │
│                   │
│  4. Deduct from   │
│     wallet        │
│                   │
│  5. Record the    │
│     transaction   │
│                   │
│  6. Check: is     │──────► If balance < threshold
│     balance low?  │
│                   │        Emit: balance.low event
└───────────────────┘                 │
                                      │
                                      ▼
                          ┌───────────────────┐
                          │ BILLING &         │
                          │ PAYMENTS          │
                          │                   │
                          │ (listening...)    │
                          │                   │
                          │ "I heard balance  │
                          │  is low, I'll     │
                          │  handle it"       │
                          └───────────────────┘
```

**What happens:** Usage Metering does its job completely. At the end, if the balance is low, it simply announces "balance is low" - it doesn't care what happens next.

---

### Flow 2: Auto Top-Up

When a customer's balance drops below their threshold, Billing automatically charges their saved payment method.

```
        balance.low event received
                    │
                    ▼
        ┌───────────────────────┐
        │  BILLING & PAYMENTS   │
        │                       │
        │  1. Look up customer's│
        │     auto-topup config │
        │                       │
        │  2. Is auto-topup     │───► No: Do nothing
        │     enabled?          │
        │           │           │
        │          Yes          │
        │           │           │
        │           ▼           │
        │  3. Get saved payment │
        │     method            │
        │                       │
        │  4. Charge the card   │
        │     via Stripe        │
        │                       │
        │  5. Did it succeed?   │───► No: Record failure,
        │           │           │         maybe notify
        │          Yes          │
        │           │           │
        │           ▼           │
        │  6. Send command:     │
        │     credit_wallet     │
        └───────────┬───────────┘
                    │
                    │  credit_wallet command
                    │  (customer_id, amount,
                    │   source="auto_topup",
                    │   reference="pi_xxx")
                    │
                    ▼
        ┌───────────────────────┐
        │   USAGE METERING      │
        │                       │
        │  1. Add amount to     │
        │     wallet balance    │
        │                       │
        │  2. Record the        │
        │     transaction       │
        │                       │
        │  3. Return success    │
        └───────────────────────┘
```

**What happens:** Billing handles all the payment complexity. Usage just receives a command to add money - it doesn't know or care that it came from a credit card.

---

### Flow 3: Manual Top-Up (Checkout)

A customer clicks "Add funds" and pays through a checkout page.

```
Customer clicks "Add $50"
            │
            ▼
    ┌───────────────────┐
    │ BILLING &         │
    │ PAYMENTS          │
    │                   │
    │ 1. Create Stripe  │
    │    checkout       │
    │    session        │
    │                   │
    │ 2. Return the     │
    │    checkout URL   │
    └─────────┬─────────┘
              │
              ▼
    Customer pays on Stripe checkout
              │
              ▼
    Stripe sends webhook: payment succeeded
              │
              ▼
    ┌───────────────────┐
    │ BILLING &         │
    │ PAYMENTS          │
    │                   │
    │ 1. Verify the     │
    │    webhook        │
    │                   │
    │ 2. Record the     │
    │    successful     │
    │    payment        │
    │                   │
    │ 3. Send command:  │
    │    credit_wallet  │
    └─────────┬─────────┘
              │
              │  credit_wallet command
              │
              ▼
    ┌───────────────────┐
    │  USAGE METERING   │
    │                   │
    │  Credit the       │
    │  wallet           │
    └───────────────────┘
```

**What happens:** Same pattern - Billing handles payment, then tells Usage to credit the wallet.

---

### Flow 4: Insufficient Balance (Suspension)

When a customer's balance hits zero and they try to use more.

```
Customer tries to use API
            │
            ▼
    ┌───────────────────┐
    │  USAGE METERING   │
    │                   │
    │  1. Check balance │
    │                   │
    │  2. Balance = 0   │
    │     Can't deduct  │
    │                   │
    │  3. Suspend the   │
    │     customer      │
    │                   │
    │  4. Emit event:   │
    │     customer.     │
    │     suspended     │
    │                   │
    │  5. Reject the    │
    │     API request   │
    └─────────┬─────────┘
              │
              │  customer.suspended event
              │
              ▼
    ┌───────────────────┐
    │ BILLING &         │
    │ PAYMENTS          │
    │                   │
    │ 1. (Optional)     │
    │    Send email     │
    │    notification   │
    │                   │
    │ 2. (Optional)     │
    │    Try emergency  │
    │    charge         │
    └───────────────────┘
```

**What happens:** Usage Metering makes the access control decision. Billing can react however it wants (or not at all).

---

### Flow 5: Refund

A customer disputes a charge or requests a refund.

```
Support initiates refund
            │
            ▼
    ┌───────────────────┐
    │ BILLING &         │
    │ PAYMENTS          │
    │                   │
    │ 1. Process refund │
    │    in Stripe      │
    │                   │
    │ 2. Send command:  │
    │    credit_wallet  │
    │    (source=refund)│
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │  USAGE METERING   │
    │                   │
    │  Credit wallet    │
    │  with refund      │
    │  amount           │
    └───────────────────┘
```

---

## The Interface Definitions

### Events (Usage → Billing)

```
balance.low
├── customer_id: UUID
├── current_balance: integer (micros)
├── threshold: integer (micros)
└── timestamp: datetime

balance.depleted
├── customer_id: UUID
├── attempted_deduction: integer (micros)
└── timestamp: datetime

customer.suspended
├── customer_id: UUID
├── reason: string ("insufficient_balance", "payment_failed", etc.)
└── timestamp: datetime
```

### Commands (Billing → Usage)

```
credit_wallet
├── customer_id: UUID
├── amount: integer (micros)
├── source: string ("manual_topup", "auto_topup", "refund", "adjustment")
├── reference: string (payment intent ID, invoice ID, etc.)
├── idempotency_key: string
└── Returns: { success: bool, new_balance: integer, transaction_id: UUID }

get_balance
├── customer_id: UUID
└── Returns: { balance: integer, currency: string }
```

---

## Why This Separation Matters

### 1. Swap Payment Providers

Want to switch from Stripe to Paddle? Only Billing changes.

```
BEFORE                              AFTER
──────                              ─────
Usage ◄──► Billing (Stripe)         Usage ◄──► Billing (Paddle)

Usage code: unchanged               Usage code: unchanged
```

### 2. Swap Metering Systems

Want to use a third-party metering service? Only Usage changes.

```
BEFORE                              AFTER
──────                              ─────
Usage (UBB) ◄──► Billing            Usage (Metronome) ◄──► Billing

Billing code: unchanged             Billing code: unchanged
```

### 3. Sell Them Separately

Some customers only need metering (they have their own billing). Some only need billing (they have their own metering).

```
Customer A: Uses both products
Customer B: Uses only Usage Metering + their own Stripe integration
Customer C: Uses only Billing & Payments + Segment for metering
```

### 4. Scale Independently

Usage recording is high-volume (millions of events). Payment processing is low-volume but high-value. They have different scaling needs.

```
Usage Metering                      Billing & Payments
──────────────                      ──────────────────
High throughput                     Low throughput
Eventually consistent OK            Strong consistency required
Can batch/buffer                    Real-time required
Horizontal scaling                  Vertical scaling often fine
```

---

## Implementation: What Changes

### Current State (Tightly Coupled)

```python
# In usage_service.py - CURRENT
def record_usage(...):
    # ... deduct wallet ...

    # Direct call to billing concern
    if wallet.balance < threshold:
        AutoTopUpService.create_pending_attempt(customer)  # ❌ Tight coupling
        charge_auto_topup_task.delay(attempt.id)           # ❌ Tight coupling
```

### Target State (Loosely Coupled)

```python
# In usage_service.py - TARGET
def record_usage(...):
    # ... deduct wallet ...

    # Emit event, don't care who handles it
    if wallet.balance < threshold:
        events.emit("balance.low", {                       # ✅ Loose coupling
            "customer_id": customer.id,
            "balance": wallet.balance,
            "threshold": threshold
        })

# In billing webhook handler - TARGET
@events.on("balance.low")
def handle_low_balance(event):
    # Billing decides what to do
    config = AutoTopUpConfig.objects.get(customer_id=event["customer_id"])
    if config.enabled:
        charge_saved_payment_method(...)
```

### The Shared Contract

```python
# shared/contracts.py

class UsageMeteringInterface:
    """What Billing can ask of Usage"""

    def credit_wallet(
        self,
        customer_id: UUID,
        amount: int,
        source: str,
        reference: str,
        idempotency_key: str
    ) -> CreditResult:
        ...

    def get_balance(self, customer_id: UUID) -> BalanceInfo:
        ...


class BillingEventsInterface:
    """What Usage tells Billing about"""

    def on_balance_low(self, handler: Callable):
        ...

    def on_customer_suspended(self, handler: Callable):
        ...
```

---

## Communication Options

### Option A: Direct Function Calls (Monolith)

Good for: Single codebase, same process

```python
# Billing calls Usage directly
from usage.services import credit_wallet
credit_wallet(customer_id, amount, ...)
```

Pros: Simple, fast, transactional
Cons: Can't deploy separately

### Option B: Internal HTTP APIs (Modular Monolith / Microservices)

Good for: Separate deployments, same team

```python
# Billing calls Usage via HTTP
response = httpx.post(
    "http://usage-service/api/internal/credit",
    json={"customer_id": str(customer_id), "amount": amount}
)
```

Pros: Can deploy separately, clear boundaries
Cons: Network overhead, need to handle failures

### Option C: Message Queue (Event-Driven)

Good for: High scale, async operations

```python
# Usage emits to queue
queue.publish("balance.low", {"customer_id": ..., "balance": ...})

# Billing subscribes
@queue.subscribe("balance.low")
def handle_low_balance(event):
    ...
```

Pros: Decoupled, scalable, resilient
Cons: Eventual consistency, more infrastructure

### Recommendation

Start with **Option A** (direct calls with clear interfaces), then evolve to **Option B** or **C** when you need to scale or sell separately.

---

## Summary

| Aspect | Usage Metering | Billing & Payments |
|--------|----------------|-------------------|
| **Core job** | Track consumption | Collect money |
| **Owns** | Events, balances, pricing | Payments, invoices, providers |
| **Emits** | balance.low, customer.suspended | credit_wallet commands |
| **Accepts** | credit_wallet, get_balance | balance events |
| **Scales** | Horizontally (high volume) | Vertically (high value) |
| **Consistency** | Eventual OK | Strong required |

**The golden rule:** Usage never touches payment providers. Billing never touches usage calculations. They communicate through events and commands.
