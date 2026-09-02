"""Tests for UBBClient delegation to product clients.

Verifies that:
1. UBBClient no longer has its own _http client
2. Billing methods raise UBBError when billing product is not enabled
3. Metering methods raise UBBError when metering product is not enabled
4. Methods properly delegate to the appropriate product client
5. create_customer uses metering's _request for the platform API
"""
import inspect

import pytest
from unittest.mock import MagicMock, patch

from ubb import UBBClient, SubscriptionsClient
from ubb.exceptions import UBBError
from ubb.metering import MeteringClient
from ubb.types import PaginatedResponse
from ubb._core.models.balance_response import BalanceResponse
from ubb._core.models.top_up_checkout_response import TopUpCheckoutResponse


class TestLegacyHTTPRemoved:
    """Verify the legacy _http client and related methods are removed."""

    def test_no_http_client(self):
        client = UBBClient(api_key="test")
        assert not hasattr(client, "_http")
        client.close()

    def test_no_request_method(self):
        client = UBBClient(api_key="test")
        assert not hasattr(client, "_request")
        client.close()

    def test_no_extract_error_detail(self):
        client = UBBClient(api_key="test")
        assert not hasattr(client, "_extract_error_detail")
        client.close()

    def test_no_billing_client_alias(self):
        client = UBBClient(api_key="test", billing=True)
        assert not hasattr(client, "billing_client")
        client.close()


class TestBillingDelegationRequiresBilling:
    """Methods that require billing raise UBBError when billing is disabled."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", metering=True, billing=False)

    def teardown_method(self):
        self.client.close()

    def test_get_balance_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.get_balance("cust1")

    def test_create_top_up_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.create_top_up("cust1", 100_000,
                                      success_url="http://ok", cancel_url="http://no",
                                      idempotency_key="tp_k")

    def test_configure_auto_top_up_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.configure_auto_top_up("cust1", threshold=0, amount=100_000)

    def test_withdraw_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.withdraw("cust1", 100_000, "w1")

    def test_refund_usage_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.refund_usage("cust1", "evt1", "r1")

    def test_get_transactions_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.get_transactions("cust1")


class TestMeteringDelegationRequiresMetering:
    """Methods that require metering raise UBBError when metering is disabled."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", metering=False, billing=True)

    def teardown_method(self):
        self.client.close()

    def test_record_usage_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.record_usage("cust1", "i1", provider_cost_micros=1000)

    def test_pre_check_without_metering_delegates_to_billing(self):
        """pre_check no longer requires metering — delegates to billing if available."""
        self.client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 5_000_000,
        })
        result = self.client.pre_check("cust1")
        assert result.allowed is True
        self.client.billing.pre_check.assert_called_once_with(
            "cust1", parent_task_id=None,
        )

    def test_get_usage_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.get_usage("cust1")

    def test_create_customer_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.create_customer("ext1")


class TestBillingDelegation:
    """Methods properly delegate to the billing product client."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", metering=True, billing=True)

    def teardown_method(self):
        self.client.close()

    def test_get_balance_delegates(self):
        expected = BalanceResponse(
            balance_micros=5_000_000, currency="USD",
            billing_owner_id="11111111-1111-1111-1111-111111111111",
            billing_owner_external_id="cust1", is_pooled_seat=False,
        )
        self.client.billing.get_balance = MagicMock(return_value=expected)
        result = self.client.get_balance("cust1")
        self.client.billing.get_balance.assert_called_once_with("cust1")
        assert result is expected

    def test_create_top_up_delegates(self):
        expected = TopUpCheckoutResponse(checkout_url="https://example.com/checkout")
        self.client.billing.create_top_up = MagicMock(return_value=expected)
        result = self.client.create_top_up("cust1", 100_000,
                                           success_url="http://ok",
                                           cancel_url="http://no",
                                           idempotency_key="tp_k")
        self.client.billing.create_top_up.assert_called_once_with(
            "cust1", 100_000, "http://ok", "http://no", "tp_k",
        )
        assert result is expected

    def test_get_transactions_delegates(self):
        expected = PaginatedResponse(data=[], next_cursor=None, has_more=False)
        self.client.billing.get_transactions = MagicMock(return_value=expected)
        result = self.client.get_transactions("cust1", limit=10)
        self.client.billing.get_transactions.assert_called_once_with(
            "cust1", cursor=None, limit=10,
        )
        assert result is expected


class TestMeteringDelegation:
    """Methods properly delegate to the metering product client."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", metering=True, billing=False)

    def teardown_method(self):
        self.client.close()

    def test_get_usage_delegates(self):
        expected = PaginatedResponse(data=[], next_cursor=None, has_more=False)
        self.client.metering.get_usage = MagicMock(return_value=expected)
        result = self.client.get_usage("cust1", limit=25)
        self.client.metering.get_usage.assert_called_once_with(
            "cust1", cursor=None, limit=25,
        )
        assert result is expected

    def test_record_usage_forwards_metrics_backdating_and_stop(self):
        """The facade passes the richer metering params through, and works
        without provider_cost_micros (metrics-only recording). The stop
        keyword forwarded is the OPT-OUT: raising is the default on both
        clients now (#421), so the value that must survive the passthrough is
        the one a caller has to spell."""
        sentinel = object()
        self.client.metering.record_usage = MagicMock(return_value=sentinel)
        result = self.client.record_usage(
            "cust1", "i1",
            measurements={"tokens": 1000},
            recorded_at="2026-06-01T00:00:00Z",
            task_id="task_1",
            raise_on_stop=False,
        )
        assert result is sentinel
        _, kwargs = self.client.metering.record_usage.call_args
        assert kwargs["measurements"] == {"tokens": 1000}
        assert kwargs["recorded_at"] == "2026-06-01T00:00:00Z"
        assert kwargs["task_id"] == "task_1"
        assert kwargs["raise_on_stop"] is False


class TestRecordUsageSignatureParity:
    """UBBClient.record_usage must be a non-lossy passthrough of
    MeteringClient.record_usage: every call the metering client accepts, the
    facade must accept too. Guards against the facade silently drifting behind
    the lower-level client (the regression that hid named-metrics and
    backdating from facade users)."""

    # Params the facade intentionally does NOT mirror (none today). Add here
    # with a comment if a deliberate divergence is ever introduced.
    KNOWN_DIVERGENCES: set = set()

    def test_facade_accepts_every_metering_param(self):
        facade = inspect.signature(UBBClient.record_usage).parameters
        lower = inspect.signature(MeteringClient.record_usage).parameters
        for name in lower:
            if name == "self" or name in self.KNOWN_DIVERGENCES:
                continue
            assert name in facade, (
                f"UBBClient.record_usage is missing '{name}', which "
                f"MeteringClient.record_usage accepts"
            )

    def test_facade_does_not_tighten_optional_params(self):
        facade = inspect.signature(UBBClient.record_usage).parameters
        lower = inspect.signature(MeteringClient.record_usage).parameters
        empty = inspect.Parameter.empty
        for name, param in lower.items():
            if name == "self" or name in self.KNOWN_DIVERGENCES:
                continue
            if param.default is not empty and name in facade:
                assert facade[name].default is not empty, (
                    f"UBBClient.record_usage made '{name}' required, but it is "
                    f"optional on MeteringClient.record_usage"
                )

    def test_facade_keeps_every_default(self):
        """Presence and optionality are not enough: a default is behaviour.
        When the spend stop started raising by default (#421) a facade left
        at the old value would have passed both checks above and handed every
        facade caller the silent path. The two signatures must agree on the
        VALUE of every shared default."""
        facade = inspect.signature(UBBClient.record_usage).parameters
        lower = inspect.signature(MeteringClient.record_usage).parameters
        empty = inspect.Parameter.empty
        compared = 0
        for name, param in lower.items():
            if name == "self" or name in self.KNOWN_DIVERGENCES:
                continue
            if param.default is empty:
                continue
            assert facade[name].default == param.default, (
                f"UBBClient.record_usage defaults '{name}' to "
                f"{facade[name].default!r}, but MeteringClient.record_usage "
                f"defaults it to {param.default!r}"
            )
            compared += 1
        assert compared > 0  # the walk compared something


class TestCloseTaskSignatureParity:
    """`UBBClient.close_task` must be a non-lossy passthrough too (#409).

    ⚠ THIS IS THE PARITY CHECK THE CLASS ABOVE ALREADY HAD FOR `record_usage`,
    AND ITS ABSENCE HERE COST A REAL BUG. When the close gained its required
    `outcome`, the facade went on calling the metering client with a task id
    alone — a `TypeError` on every call through `UBBClient`, with the whole SDK
    suite green because nothing exercised the facade's close at all. Generalised
    rather than copied: one list, both methods, so the third facade method to
    grow an argument is covered on the day it does.
    """

    #: (facade method, metering method) pairs the facade must mirror in full.
    #: Params intentionally NOT mirrored go in `KNOWN_DIVERGENCES` with a
    #: comment; there are none today for any of them. The unit-of-work
    #: surface joined in #422: the start, and the three reads that arrived
    #: with it.
    PASSTHROUGHS = ("record_usage", "close_task", "start_task", "get_task",
                    "list_tasks", "list_subtasks")
    KNOWN_DIVERGENCES: set = set()

    def test_every_facade_passthrough_accepts_every_lower_param(self):
        for method in self.PASSTHROUGHS:
            facade = inspect.signature(getattr(UBBClient, method)).parameters
            lower = inspect.signature(getattr(MeteringClient, method)).parameters
            for name in lower:
                if name == "self" or name in self.KNOWN_DIVERGENCES:
                    continue
                assert name in facade, (
                    f"UBBClient.{method} is missing '{name}', which "
                    f"MeteringClient.{method} accepts"
                )

    def test_the_facade_close_actually_forwards_the_declaration(self):
        """A signature can match while the body drops an argument, which is a
        different failure and the one that reaches a caller."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        sentinel = object()
        client.metering.close_task = MagicMock(return_value=sentinel)

        result = client.close_task("task_1", "delivered",
                                   outcome_reason="timeout",
                                   reason_detail="took too long")

        assert result is sentinel
        args, kwargs = client.metering.close_task.call_args
        assert args == ("task_1", "delivered")
        assert kwargs == {"outcome_reason": "timeout",
                          "reason_detail": "took too long"}
        client.close()

    def test_the_facade_close_requires_an_outcome(self):
        """No default on the facade either: the forgiving path must never be
        the money-moving one, at any layer."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        client.metering.close_task = MagicMock()
        with pytest.raises(TypeError):
            client.close_task("task_1")
        client.close()

    def test_the_facade_start_forwards_the_declaration_and_hands_back_the_handle(self):
        """The facade's start is the metering client's start: every field
        reaches it under its own name and what comes back is the handle
        itself, so the work block reads the same through either client."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        sentinel = object()
        client.metering.start_task = MagicMock(return_value=sentinel)

        result = client.start_task("c1", "nightly-42", task_type="render",
                                   parent_task_id="task_0",
                                   provider_cost_limit_micros=5_000_000,
                                   external_task_id="run-7",
                                   metadata={"report": "weekly"})

        assert result is sentinel
        args, kwargs = client.metering.start_task.call_args
        assert args == ("c1", "nightly-42")
        assert kwargs["task_type"] == "render"
        assert kwargs["parent_task_id"] == "task_0"
        assert kwargs["provider_cost_limit_micros"] == 5_000_000
        assert kwargs["external_task_id"] == "run-7"
        assert kwargs["metadata"] == {"report": "weekly"}
        client.close()

    def test_the_facade_start_requires_the_key(self):
        """A PIN of the facade's signature, asserted by the parameter's name:
        the key is the retry story and the reason the route requires it, and
        a facade that defaulted it would mint a new unit of work per retry."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        client.metering.start_task = MagicMock()
        with pytest.raises(TypeError, match="idempotency_key"):
            client.start_task("c1")
        client.close()

    def test_the_facade_reads_forward_their_filters(self):
        client = UBBClient(api_key="test", metering=True, billing=False)
        for method, args, kwargs in (
            ("get_task", ("task_1",), {}),
            ("list_tasks", (), {"cursor": "c", "limit": 5, "customer_id": "c1",
                                "task_type": "render", "status": "active"}),
            ("list_subtasks", ("task_1",), {"cursor": "c", "limit": 5}),
        ):
            sentinel = object()
            setattr(client.metering, method, MagicMock(return_value=sentinel))
            assert getattr(client, method)(*args, **kwargs) is sentinel
            getattr(client.metering, method).assert_called_once_with(
                *args, **kwargs)
        client.close()


class TestCreateCustomerDelegation:
    """create_customer uses metering._request to call the platform API."""

    def test_create_customer_uses_metering_request(self):
        client = UBBClient(api_key="test", metering=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "c1", "external_id": "ext1", "status": "active", "stripe_customer_id": "cus_123",
        }
        client.metering._request = MagicMock(return_value=mock_response)

        result = client.create_customer("ext1", stripe_customer_id="cus_123")

        client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/customers", json={
                "external_id": "ext1",
                "stripe_customer_id": "cus_123",
                "metadata": {},
                "account_type": "individual",
                "parent_external_id": "",
                "billing_topology": "",
            }
        )
        assert result.external_id == "ext1"
        assert result.id == "c1"
        client.close()


class TestSubscriptionsExport:
    """SubscriptionsClient is exported from ubb package."""

    def test_subscriptions_client_importable(self):
        from ubb import SubscriptionsClient
        assert SubscriptionsClient is not None

    def test_subscriptions_client_in_all(self):
        import ubb
        assert "SubscriptionsClient" in ubb.__all__


class TestCloseNoHTTP:
    """close() does not reference _http."""

    def test_close_only_closes_product_clients(self):
        client = UBBClient(api_key="test", metering=True, billing=True,
                           subscriptions=True, referrals=True)
        with patch.object(client.metering, "close") as m_close, \
             patch.object(client.billing, "close") as b_close, \
             patch.object(client.subscriptions, "close") as s_close, \
             patch.object(client.referrals, "close") as r_close:
            client.close()
            m_close.assert_called_once()
            b_close.assert_called_once()
            s_close.assert_called_once()
            r_close.assert_called_once()

    def test_close_with_none_clients_does_not_error(self):
        client = UBBClient(api_key="test", metering=False, billing=False)
        client.close()  # Should not raise


class TestPreCheckWithoutEventType:
    """pre_check without event_type should work with the new delegation model."""

    def test_pre_check_metering_only_no_event_type(self):
        """With metering only, no event_type: trivially allowed."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        result = client.pre_check(customer_id="cust1")
        assert result.allowed is True
        assert result.can_proceed is True
        client.close()

    def test_pre_check_with_billing_delegates(self):
        """With billing enabled, delegates to billing.pre_check."""
        client = UBBClient(api_key="test", metering=True, billing=True)
        client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 5_000_000,
        })
        result = client.pre_check(customer_id="cust1")
        client.billing.pre_check.assert_called_once_with(
            "cust1", parent_task_id=None,
        )
        assert result.allowed is True
        assert result.balance_micros == 5_000_000
        client.close()
