"""
Security utilities — credential masking, URL sanitization.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def mask_url(url: str) -> str:
    """Replace embedded credentials in a URL with asterisks.

    Example:
        rtsp://admin:secret@192.168.1.1:554/stream
        → rtsp://admin:***@192.168.1.1:554/stream
    """
    try:
        parsed = urlparse(url)
        if parsed.username:
            masked_pass = "***" if parsed.password else ""
            auth = f"{parsed.username}:{masked_pass}@" if parsed.password else f"{parsed.username}@"
            return urlunparse(parsed._replace(netloc=auth + parsed.hostname + (f":{parsed.port}" if parsed.port else "")))
    except Exception:
        pass
    return url


def mask_credentials(text: str) -> str:
    """Mask password-like substrings in any text.

    Patterns covered:
        password=secret
        password: secret
        :secret@host
    """
    text = re.sub(r"(password[=:\s]+)\S+", r"\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", text)
    return text


def sanitize_for_log(value: str) -> str:
    """Sanitize a string for safe logging."""
    return mask_credentials(mask_url(value))
