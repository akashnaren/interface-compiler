"""Map inputs and outputs. Provisional ids; the registry finalizes them later."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from interface_compiler.browser.facts import ElementFact
from interface_compiler.contract.models import Affordance, AffordanceX, InputSchema, Locator
from interface_compiler.extract.lexicon import Lexicon
from interface_compiler.extract.naming import normalize_label, slug

_DIGIT = re.compile(r"\d")


@dataclass(frozen=True, slots=True)
class MapContext:
    page_url: str
    view_hint: str | None = None
    landmark_names: dict[str, str] = field(default_factory=dict)
    lexicon: Lexicon = field(default_factory=Lexicon)
    namer: None = None
    include_secondary: tuple[str, ...] = ()
    signed_in: bool = False


@dataclass
class MapResult:
    affordances: list[Affordance] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    state_from: dict[str, str] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    entities_from: dict[str, str] = field(default_factory=dict)
    page: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    view: str | None = None


def merge_results(parts: list[MapResult]) -> MapResult:
    merged = MapResult()
    for part in parts:
        merged.affordances.extend(part.affordances)
        merged.state.update(part.state)
        merged.state_from.update(part.state_from)
        for key, value in part.entities.items():
            merged.entities[key] = value
        merged.entities_from.update(part.entities_from)
        merged.page.update(part.page)
        for key, rows in part.catalog.items():
            merged.catalog.setdefault(key, []).extend(rows)
        if part.view:
            merged.view = part.view
    return merged


def empty_input() -> InputSchema:
    return InputSchema.model_validate({"type": "object", "properties": {}})


def input_schema(
    properties: dict[str, dict[str, object]],
    required: list[str] | None = None,
) -> InputSchema:
    payload: dict[str, object] = {"type": "object", "properties": properties}
    if required:
        payload["required"] = required
    return InputSchema.model_validate(payload)


def affordance(
    affordance_id: str,
    *,
    enabled: bool,
    schema: InputSchema | None = None,
    label: str,
    locator: Locator,
    grain: str,
    tag: str,
    reason: str | None = None,
    signature: str | None = None,
) -> Affordance:
    extra = AffordanceX(
        reason=reason,
        tag=tag,  # type: ignore[arg-type]
        label=label,
        locator=locator,
        signature=signature,
        grain=grain,  # type: ignore[arg-type]
        source="compiled",
        verified="unverified",
    )
    return Affordance(
        id=affordance_id,
        enabled=enabled,
        input=schema or empty_input(),
        x=extra,
    )


def ax_locator(element: ElementFact, **extra: object) -> Locator:
    payload: dict[str, object] = {
        "kind": "ax",
        "role": element.role,
        "name": element.name,
        "landmark": element.landmark or None,
        "nth": 0,
        "css": element.css or None,
        "named_by": "rule",
        "html_id": element.html_id,
        "in_dialog": element.in_dialog,
    }
    payload.update(extra)
    return Locator.model_validate(payload)


def stable_signature(*parts: str) -> str:
    normalized = []
    for part in parts:
        text = " ".join(part.casefold().split())
        normalized.append(_DIGIT.sub("#", text))
    digest = hashlib.sha1("|".join(normalized).encode()).hexdigest()
    return digest[:12]


def button_id(label: str, lexicon: Lexicon) -> str:
    verb = lexicon.verb(label)
    if verb:
        return verb
    text = slug(label) or "action"
    if lexicon.verb(text.split("_", 1)[0]):
        return text
    return f"do_{text}"


def link_id(element: ElementFact, ctx: MapContext) -> str:
    href = element.href or ""
    parsed = urlsplit(href)
    page = urlsplit(ctx.page_url)
    if parsed.fragment and parsed.path == page.path and parsed.query == page.query:
        anchor = slug(parsed.fragment) or "section"
        return f"go_{anchor}"
    view = ctx.lexicon.view_for_href(href)
    if view and view != "home":
        return f"go_{view}"
    text = slug(element.name) or "link"
    return f"go_{text}"


def login_gated(element: ElementFact, ctx: MapContext, affordance_id: str) -> bool:
    if affordance_id == "go_sign_in" or ctx.signed_in:
        return False
    if ctx.lexicon.login_label(element.name) or ctx.lexicon.login_label(element.label_text):
        return True
    for target in (element.href, element.form_action):
        if target and ctx.lexicon.login_target(target):
            return True
    return False


def apply_hard_block(
    enabled: bool,
    reason: str | None,
    verb: str | None,
    lexicon: Lexicon,
) -> tuple[bool, str | None]:
    blocked = lexicon.hard_block(verb)
    if blocked and enabled:
        return False, blocked
    if blocked and reason is None:
        return False, blocked
    return enabled, reason


def normalize(text: str) -> str:
    return normalize_label(text)
