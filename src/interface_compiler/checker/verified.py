"""A mutating affordance on a real site cannot reach ``probed_ok``.

Loopback fixture hosts (``127.0.0.1``, ``localhost``, ``::1``) may record that
outcome. Any other host, and a document with no page URL, may not. A missing
tag is treated as mutating. This module reads ``x.url``, ``x.tag``, and
``x.verified`` only.
"""

from __future__ import annotations

from collections.abc import Mapping

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_HTTP_SCHEMES = frozenset({"http", "https"})
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
    """True only for an http(s) URL whose host is exactly a loopback name.

    The host is taken from the authority, not from ``urlsplit``. A userinfo
    trick such as ``http://evil.com\\@127.0.0.1/`` must not count: Chromium
    navigates to the name before the backslash. Backslashes, whitespace,
    control characters, userinfo, and any scheme other than http or https
    fail closed. An explicit port must be one to five ASCII digits and an
    integer from 1 to 65535. Any other port is not loopback.
    """
    if not isinstance(url, str) or url == "":
        return False
    if _forbidden_url_char(url):
        return False
    scheme, separator, rest = url.partition("://")
    if separator != "://" or scheme.lower() not in _HTTP_SCHEMES:
        return False
    authority = _authority(rest)
    if authority == "" or "@" in authority:
        return False
    host, port = _host_and_port(authority)
    if host is None or host.lower() not in _LOOPBACK_HOSTS:
        return False
    if port is None:
        return True
    # Unicode digits pass str.isdigit and can make int() raise or accept a port.
    if not (port.isascii() and port.isdigit() and len(port) <= 5):
        return False
    number = int(port)
    return 1 <= number <= 65535


def _forbidden_url_char(url: str) -> bool:
    for char in url:
        if char == "\\" or char.isspace() or ord(char) < 32 or ord(char) == 127:
            return True
    return False


def _authority(rest: str) -> str:
    authority = rest
    for marker in "/?#":
        index = authority.find(marker)
        if index != -1:
            authority = authority[:index]
    return authority


def _host_and_port(authority: str) -> tuple[str | None, str | None]:
    if authority.startswith("["):
        end = authority.find("]")
        if end < 2:
            return None, None
        host = authority[1:end]
        # Bracketed hosts are IPv6. Only the exact loopback address counts.
        if host.lower() != "::1":
            return None, None
        tail = authority[end + 1 :]
        if tail == "":
            return host, None
        if len(tail) < 2 or not tail.startswith(":"):
            return None, None
        return host, tail[1:]
    if ":" not in authority:
        return authority, None
    host, port = authority.rsplit(":", 1)
    if host == "" or port == "" or ":" in host:
        return None, None
    return host, port
