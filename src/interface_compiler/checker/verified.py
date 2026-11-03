"""A mutating affordance on a real site cannot reach ``probed_ok``.

Loopback fixture hosts (``127.0.0.1``, ``localhost``, ``::1``) may record that
outcome. Any other host, and a document with no page URL, may not. A missing
tag is treated as mutating. This module reads ``x.url``, ``x.tag``, and
``x.verified`` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_BAN = "mutating affordance cannot be probed_ok"


def probed_ok_refusal(tag: object, verified: object, *, page_url: object) -> str | None:
    """Return the ban message, or ``None`` when this outcome is allowed."""
    if verified != "probed_ok":
        return None
    if tag == "safe":
        return None
    if _is_loopback(page_url):
        return None
    return _BAN


def verified_errors(instance: object, *, prefix: str = "") -> list[str]:
    """Error strings for illegal ``probed_ok`` values in a document or act response."""
    if not isinstance(instance, Mapping):
        return []
    errors: list[str] = []
    page_url = _page_url(instance)
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            extra = item.get("x")
            if not isinstance(extra, Mapping):
                continue
            message = probed_ok_refusal(
                extra.get("tag"),
                extra.get("verified"),
                page_url=page_url,
            )
            if message is None:
                continue
            where = f"{prefix}affordances/{index}/x/verified"
            errors.append(f"{where}: {message}")
    nested = instance.get("doc")
    if isinstance(nested, Mapping):
        errors.extend(verified_errors(nested, prefix=f"{prefix}doc/"))
    return errors


def _page_url(instance: Mapping[object, object]) -> object:
    extra = instance.get("x")
    if not isinstance(extra, Mapping):
        return None
    return extra.get("url")


def _is_loopback(url: object) -> bool:
    if not isinstance(url, str) or url == "":
        return False
    try:
        host = urlsplit(url).hostname
    except (ValueError, UnicodeError):
        return False
    if not isinstance(host, str):
        return False
    return host.lower() in _LOOPBACK_HOSTS
