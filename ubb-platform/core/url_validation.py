import ipaddress
import socket
from urllib.parse import urlparse


def validate_webhook_url(url: str) -> None:
    """Validate a webhook URL is safe to deliver to.

    Rejects:
    - Non-HTTPS schemes
    - Private/internal IP addresses (RFC 1918, loopback, link-local)
    - AWS metadata endpoint (169.254.169.254)
    """
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a hostname")

    # Check for obvious private hostnames
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("Webhook URL must not point to private/internal addresses")

    # Resolve hostname and check IP
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Webhook URL must not point to private/internal addresses")
