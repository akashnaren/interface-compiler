"""Verb, view, and login-gate lexicons. The first matching pattern wins."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qsl, urlsplit

from interface_compiler.extract.naming import normalize_label

# Hard-block verbs are matched before mutating verbs, then safe verbs.
_HARD = frozenset({"pay", "place_order", "checkout_submit", "delete", "send", "upload"})
_MUTATING = frozenset(
    {
        "add_to_cart",
        "add_to_wishlist",
        "subscribe",
        "sign_in",
        "sign_out",
        "register",
        "apply_coupon",
        "update_quantity",
        "remove_from_cart",
        "save",
        "submit",
        "vote",
        "like",
        "follow",
        "book",
        "reserve",
    }
)
_VERBS: tuple[tuple[str, str], ...] = (
    ("pay", r"pay(?: now)?|complete (?:purchase|payment)|submit payment"),
    ("place_order", r"place (?:my |your )?order|confirm (?:order|purchase)|buy now|purchase"),
    ("delete", r"delete|remove (?:account|address|card)|close account"),
    ("send", r"send(?: message)?|post(?: comment| reply)?|publish|tweet|submit (?:review|comment)"),
    ("add_to_cart", r"add to (?:cart|bag|basket|trolley)"),
    ("add_to_wishlist", r"add to wishlist"),
    ("subscribe", r"subscribe|sign up|join|newsletter"),
    ("sign_in", r"sign in|log in|login"),
    ("sign_out", r"sign out|log out|logout"),
    ("register", r"register|create account"),
    ("apply_coupon", r"apply coupon"),
    ("update_quantity", r"update quantity"),
    ("remove_from_cart", r"remove from (?:cart|bag|basket)"),
    ("save", r"save"),
    ("submit", r"submit"),
    ("vote", r"vote"),
    ("like", r"like"),
    ("follow", r"follow"),
    ("book", r"book"),
    ("reserve", r"reserve"),
    ("search", r"search"),
    ("show_more", r"show more"),
    ("next_page", r"next|›|»|more|load more|show more results"),
    ("prev_page", r"prev(?:ious)?|‹|«"),
    ("filter", r"filter"),
    ("sort", r"sort(?: by)?"),
    ("expand", r"expand"),
    ("collapse", r"collapse"),
    ("close_dialog", r"close|×|dismiss|no thanks"),
    ("accept_cookies", r"accept cookies"),
    ("reject_cookies", r"reject cookies"),
    ("open_menu", r"open menu"),
    ("play", r"play"),
    ("pause", r"pause"),
    ("share", r"share"),
    ("copy", r"copy"),
    ("print", r"print"),
    ("download", r"download"),
    ("go_back", r"back(?: to .+)?|go back"),
)
_HARD_LABELS: tuple[tuple[str, str], ...] = (
    ("pay", r"pay(?: now)?|complete (?:purchase|payment)|submit payment"),
    ("place_order", r"place (?:my |your )?order|confirm (?:order|purchase)|buy now|purchase"),
    ("delete", r"delete|remove (?:account|address|card)|close account"),
    ("send", r"send(?: message)?|post(?: comment| reply)?|publish|tweet|submit (?:review|comment)"),
    ("upload", r"upload"),
)
# A hard-block verb matches as a leading phrase, so "Delete account" and
# "Pay 49.99" count. The rest of the lexicon still matches the whole label.
_HARD_COMPILED = tuple(
    (verb, re.compile(rf"(?:{pattern})(?:\s|$)")) for verb, pattern in _HARD_LABELS
)
_COMPILED = tuple((verb, re.compile(rf"^(?:{pattern})$")) for verb, pattern in _VERBS)
_AMOUNT = re.compile(r"\d+")
_REDIRECT = frozenset({"next", "return", "return_to", "returnto", "returnurl", "redirect", "goto"})
_VIEWS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|/)(?:cart|bag|basket)(?:/|$)"), "cart"),
    (re.compile(r"(?:^|/)checkout(?:/|$)"), "checkout"),
    (re.compile(r"(?:^|/)(?:search|results)(?:/|$)"), "search_results"),
    (re.compile(r"(?:^|/)(?:login|signin|sign-in)(?:/|$)"), "sign_in"),
    (re.compile(r"(?:^|/)(?:account|profile)(?:/|$)"), "account"),
    (re.compile(r"(?:^|/)wiki(?:/|$)"), "article"),
    (re.compile(r"(?:^|/)(?:docs|documentation|reference)(?:/|$)"), "docs"),
    (re.compile(r"(?:^|/)(?:news|article|story)(?:/|$)"), "article"),
    (re.compile(r"(?:^|/)(?:category|collections?|shop|products)(?:/|$)"), "catalog"),
    (re.compile(r"(?:^|/)(?:product|item|p|dp)(?:/|$)"), "product"),
)
_LOGIN_PATH = re.compile(
    r"(?:^|/)(?:login|signin|sign-in|account/login|auth|session/new)(?:/|$)",
    re.IGNORECASE,
)
_LOGIN_LABEL = re.compile(r"^(?:(?:sign|log) ?in to |login required|members only|account required)")
# "members only" has to finish the hint. "members only pricing" is not a sign-in cue.
_LOGIN_HINT = re.compile(
    r"\b(?:(?:sign|log) ?in to|login required|account required)\b|\bmembers only\b(?!\s+\S)"
)
# Social and account verbs, plus the same words when they are the URL path.
_ACCOUNT = frozenset(
    {
        "vote",
        "like",
        "follow",
        "comment",
        "save",
        "reply",
        "flag",
        "subscribe",
        "register",
        "book",
        "reserve",
    }
)


@dataclass(frozen=True, slots=True)
class Lexicon:
    """The fixed verb and route tables. Models may rename; they do not add verbs."""

    def verb(self, label: str) -> str | None:
        text = _strip_amounts(normalize_label(label))
        if not text:
            return None
        for name, pattern in _HARD_COMPILED:
            if pattern.match(text):
                return name
        for name, pattern in _COMPILED:
            if pattern.fullmatch(text):
                return name
        return None

    def tag(self, verb: str | None, *, method: str | None = None) -> str:
        if verb in _HARD or verb in _MUTATING:
            return "mutating"
        if method and method.lower() not in {"get", "head", ""}:
            return "mutating"
        if verb is None:
            return "mutating"
        return "safe"

    def hard_block(self, verb: str | None) -> str | None:
        if verb in _HARD:
            return f"hard-blocked in v1: {verb}"
        return None

    def view_for_href(self, href: str) -> str | None:
        parsed = urlsplit(href)
        path = parsed.path or "/"
        if path == "/":
            return "home"
        if re.search(r"(?:^|[?&])q=", parsed.query):
            return "search_results"
        for pattern, view in _VIEWS:
            if pattern.search(path):
                return view
        return None

    def login_label(self, label: str) -> bool:
        return _LOGIN_LABEL.search(normalize_label(label)) is not None

    def login_hint(self, text: str) -> bool:
        """Sign-in hint for title and aria-describedby text."""
        return _LOGIN_HINT.search(normalize_label(text)) is not None

    def account_action(self, *, label: str = "", url: str = "") -> bool:
        """True when the label, or the last path segment, is an account verb.

        ``/item/3/like`` is an action. ``/book/odyssey`` is a resource path.
        """
        verb = self.verb(label) if label else None
        if verb in _ACCOUNT:
            return True
        parts = [part.casefold() for part in urlsplit(url).path.split("/") if part]
        return bool(parts) and parts[-1] in _ACCOUNT

    def login_target(self, url: str, *, account_action: bool = False) -> bool:
        """A redirect gates when its path is a login route, on any host.

        An account-action link or form also gates when the param points back
        at this site. Other relative values, including ``next=/products``, do not.
        """
        parsed = urlsplit(url)
        if _login_path(parsed.path):
            return True
        for key, value in parse_qsl(parsed.query, keep_blank_values=False):
            if key.lower() not in _REDIRECT or not value:
                continue
            target = urlsplit(value)
            if _login_path(target.path):
                return True
            if account_action and _points_back(parsed, target):
                return True
        return False


def _strip_amounts(text: str) -> str:
    return " ".join(part for part in text.split() if _AMOUNT.fullmatch(part) is None)


def _login_path(path: str) -> bool:
    return _LOGIN_PATH.search(path or "") is not None


def _points_back(page: SplitResult, target: SplitResult) -> bool:
    """Relative targets and same-host absolute targets point at this site."""
    if target.scheme or target.netloc:
        return bool(page.netloc) and target.netloc.casefold() == page.netloc.casefold()
    return True
