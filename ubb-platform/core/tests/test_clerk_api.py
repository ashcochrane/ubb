from unittest.mock import patch, Mock

import pytest
import requests

from core.clerk_api import ClerkAPIError, get_clerk_user


@pytest.fixture
def mock_settings(settings):
    settings.CLERK_SECRET_KEY = "sk_test_fake"
    return settings


def test_returns_user_data_on_200(mock_settings):
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "id": "user_abc",
        "email_addresses": [{"email_address": "ash@example.com", "id": "em_1"}],
        "primary_email_address_id": "em_1",
    }
    fake_response.raise_for_status = Mock()
    with patch("core.clerk_api.requests.get", return_value=fake_response) as mock_get:
        user = get_clerk_user("user_abc")
    assert user["email"] == "ash@example.com"
    assert user["clerk_user_id"] == "user_abc"
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.clerk.com/v1/users/user_abc"
    assert kwargs["headers"]["Authorization"] == "Bearer sk_test_fake"


def test_raises_when_secret_missing(settings):
    settings.CLERK_SECRET_KEY = ""
    with pytest.raises(ClerkAPIError, match="CLERK_SECRET_KEY not configured"):
        get_clerk_user("user_abc")


def test_raises_on_404(mock_settings):
    fake_response = Mock(status_code=404)
    fake_response.raise_for_status.side_effect = requests.HTTPError("404")
    with patch("core.clerk_api.requests.get", return_value=fake_response):
        with pytest.raises(ClerkAPIError):
            get_clerk_user("user_missing")


def test_raises_on_timeout(mock_settings):
    with patch("core.clerk_api.requests.get", side_effect=requests.Timeout()):
        with pytest.raises(ClerkAPIError):
            get_clerk_user("user_abc")


def test_raises_when_no_primary_email(mock_settings):
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "id": "user_abc",
        "email_addresses": [],
        "primary_email_address_id": None,
    }
    fake_response.raise_for_status = Mock()
    with patch("core.clerk_api.requests.get", return_value=fake_response):
        with pytest.raises(ClerkAPIError, match="no primary email"):
            get_clerk_user("user_abc")
