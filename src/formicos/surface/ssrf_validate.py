"""Metadata endpoint validation — blocks SSRF to cloud metadata services.

Validates model registry endpoints at startup. Allows legitimate targets:
localhost, Docker service names, LAN addresses, and public cloud APIs.
Blocks cloud metadata endpoints (169.254.169.254, metadata.google.internal)
that could leak instance credentials if a model endpoint were misconfigured.

Run at startup only, not per-request.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Docker Compose service names used by FormicOS
_DOCKER_SERVICES = frozenset({
    "llm", "qdrant", "formicos-embed", "llm-swarm", "docker-proxy", "ollama",
})

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104

# Cloud metadata hostnames
_BLOCKED_HOSTS = frozenset({"metadata.google.internal", "metadata"})

# Cloud metadata IPs (AWS, ECS, Alibaba)
_BLOCKED_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
})


def validate_endpoint_url(url: str) -> None:
    """Raise ``ValueError`` if *url* targets a cloud metadata endpoint.

    Allows localhost, Docker service names, and private/LAN addresses.
    Only blocks known metadata targets and link-local IPs.
    """
    if not url:
        return

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return

    # Always allow Docker service names and localhost
    if hostname in _DOCKER_SERVICES or hostname in _LOCAL_HOSTS:
        return

    # Block known metadata hostnames
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked metadata host: {hostname}")

    # Check if hostname is a literal IP
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Not an IP — try DNS resolution
        try:
            resolved = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(resolved)
        except (socket.gaierror, OSError):
            # Can't resolve — allow (could be an external API)
            return

    if addr in _BLOCKED_IPS:
        raise ValueError(f"Blocked metadata address: {addr}")

    if addr.is_link_local:
        raise ValueError(f"Blocked link-local address: {addr}")


__all__ = ["validate_endpoint_url"]
