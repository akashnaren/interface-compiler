"""Slugs and field names. Aliases are applied after the slug."""

from __future__ import annotations

import re
import unicodedata

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.confusables import FOLDS

# Blank letters and format marks that are not caught by Mn/Me/Cf alone.
_IGNORABLE = frozenset(
    chr(code) for code in (0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0)
)

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
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def slug(text: str, *, limit: int = 32) -> str:
    """Lowercase ASCII slug, at most ``limit`` characters, no leading digit."""
    chars: list[str] = []
    for char in match_key(text):
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


def match_keys(text: str) -> tuple[str, str]:
    """Spaced and no-space keys for hard matching. Display text stays untouched."""
    kept: list[str] = []
    for char in unicodedata.normalize("NFKD", text):
        if char in _IGNORABLE or unicodedata.category(char) in {"Mn", "Me", "Cf"}:
            continue
        if unicodedata.category(char).startswith("Z"):
            kept.append(" ")
            continue
        kept.append(char)
    folded = "".join(kept).casefold()
    chars = [char if char.isalnum() or char.isspace() else " " for char in folded]
    spaced = " ".join("".join(chars).split())
    return spaced, spaced.replace(" ", "")


def match_key(text: str) -> str:
    return match_keys(text)[0]


def skeleton(text: str) -> str:
    """UTS #39 skeleton: NFKC, drop Cf, fold confusable letters to ASCII."""
    if text.isascii():
        return text
    chars: list[str] = []
    for char in unicodedata.normalize("NFKC", text):
        if unicodedata.category(char) == "Cf":
            continue
        chars.append(FOLDS.get(char, char))
    return "".join(chars)


def split_words(text: str) -> str:
    """Split camelCase and snake_case into words for the lexicon."""
    return _CAMEL_BOUNDARY.sub(r"\1 \2", text).replace("_", " ").replace("-", " ")


def normalize_label(text: str) -> str:
    return match_key(text)
