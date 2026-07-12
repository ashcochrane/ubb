import socket
from unittest.mock import patch

import pytest
from core.url_validation import validate_webhook_url


class TestWebhookUrlValidation:
    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("http://localhost:8080/hook")

    def test_rejects_localhost_https(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://localhost:8080/hook")

    def test_rejects_127(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://127.0.0.1/hook")

    def test_rejects_metadata_endpoint(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://169.254.169.254/latest/meta-data/")

    def test_rejects_rfc1918_10(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://10.0.0.1/hook")

    def test_rejects_rfc1918_172(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://172.16.0.1/hook")

    def test_rejects_rfc1918_192(self):
        with pytest.raises(ValueError, match="private"):
            validate_webhook_url("https://192.168.1.1/hook")

    def test_rejects_http_scheme(self):
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("http://example.com/hook")

    def test_accepts_valid_https(self):
        validate_webhook_url("https://example.com/webhook")  # Should not raise

    def test_rejects_non_url(self):
        with pytest.raises(ValueError):
            validate_webhook_url("not-a-url")

    def test_returns_validated_public_ip(self):
        """validate_webhook_url returns the first resolved public IP string."""
        public_ip = "1.2.3.4"  # routable public IP
        fake_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (public_ip, 0)),
        ]
        with patch("core.url_validation.socket.getaddrinfo", return_value=fake_addr_info):
            result = validate_webhook_url("https://example.com/hook")
        assert result == public_ip

    def test_returns_first_ip_when_multiple_addrs(self):
        """When getaddrinfo returns multiple records, the first acceptable IP is returned."""
        first_ip = "8.8.8.8"   # routable public IP
        second_ip = "1.1.1.1"  # routable public IP
        fake_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (first_ip, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (second_ip, 0)),
        ]
        with patch("core.url_validation.socket.getaddrinfo", return_value=fake_addr_info):
            result = validate_webhook_url("https://example.com/hook")
        assert result == first_ip
