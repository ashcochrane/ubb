import jwt
from ubb.client import UBBClient


def test_create_widget_token():
    client = UBBClient(
        api_key="ubb_test_abc123",
        base_url="http://localhost:8001",
        widget_secret="test_secret_key_1234567890",
        tenant_id="tid_abc123",
    )
    token = client.create_widget_token(customer_id="cust_abc123")
    decoded = jwt.decode(token, "test_secret_key_1234567890", algorithms=["HS256"])
    assert decoded["sub"] == "cust_abc123"
    assert decoded["tid"] == "tid_abc123"
    assert decoded["iss"] == "ubb"
    assert "exp" in decoded


def test_create_widget_token_no_secret_raises():
    client = UBBClient(api_key="ubb_test_abc123")
    try:
        client.create_widget_token(customer_id="cust_abc123")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_create_widget_token_no_tenant_id_raises():
    client = UBBClient(api_key="ubb_test_abc123", widget_secret="secret")
    try:
        client.create_widget_token(customer_id="cust_abc123")
        assert False, "Should have raised"
    except ValueError:
        pass
