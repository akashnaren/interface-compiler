"""Slugs and field names. Aliases are applied after the slug."""

from __future__ import annotations

import re

from interface_compiler.browser.facts import ElementFact

_ALIAS = (
    (re.compile(r"^(?:q|s|query|search|keywords?|k|search_query|search_term_string)$"), "query"),
    (re.compile(r"^(?:e_mail|mail|email_address)$"), "email"),
    (re.compile(r"^(?:zip|postcode|postal)$"), "postal_code"),
)
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HASH = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)


def slug(text: str, *, limit: int = 32) -> str:
    """Lowercase ASCII slug, at most ``limit`` characters, no leading digit."""
    chars: list[str] = []
    for char in text.lower():
        chars.append(char if char.isascii() and char.isalnum() else "_")
    collapsed = "".join(chars)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    collapsed = collapsed.strip("_")
    while collapsed[:1].isdigit():
        collapsed = collapsed[1:].lstrip("_")
    return collapsed[:limit].strip("_")


def alias(name: str) -> str:
    for pattern, canonical in _ALIAS:
        if pattern.fullmatch(name):
            return canonical
    return name


def cryptic(name: str) -> bool:
    letters = sum(char.isalpha() for char in name)
    if letters < 2 or "[" in name:
        return True
    return _UUID.fullmatch(name) is not None or _HASH.fullmatch(name) is not None


def field_name(element: ElementFact, *, index: int = 1) -> str:
    """Label, then an aliased name, placeholder, id, then ``field_<n>``."""
    label = slug(element.label_text) if element.label_text else ""
    if label:
        return alias(label)
    if element.field_name:
        # Alias q -> query before the cryptic check, so a one-letter q survives.
        aliased = alias(slug(element.field_name))
        if aliased and not cryptic(aliased):
            return aliased
    placeholder = slug(element.placeholder) if element.placeholder else ""
    if placeholder:
        return alias(placeholder)
    if element.html_id:
        named = slug(element.html_id)
        if named:
            return alias(named)
    return f"field_{index}"


def plural(name: str) -> str:
    if name.endswith("s"):
        return name
    if len(name) > 1 and name.endswith("y") and name[-2] not in "aeiou":
        return name[:-1] + "ies"
    return name + "s"


def normalize_label(text: str) -> str:
    chars: list[str] = []
    for char in text.casefold():
        chars.append(char if char.isalnum() or char.isspace() else " ")
    return " ".join("".join(chars).split())
