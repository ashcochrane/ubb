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
