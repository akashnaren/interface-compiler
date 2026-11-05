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
from interface_compiler.extract.naming import match_key, normalize_label, slug, suspect_label

_DIGIT = re.compile(r"\d")
_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_SOURCES: dict[int, tuple[str, ...]] = {}
_ELEMENTS: dict[int, tuple[ElementFact, ...]] = {}
_URLS: dict[int, tuple[str, ...]] = {}


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


def name_sources(element: ElementFact) -> tuple[str, ...]:
    found: list[str] = []
    for text in (
        element.name,
        element.label_text,
        element.value or "",
        element.title,
        element.described_by,
        *element.text_alternatives,
    ):
        if text and text not in found:
            found.append(text)
    return tuple(found)


def note_sources(locator: Locator, *elements: ElementFact, urls: tuple[str, ...] = ()) -> None:
    key = id(locator)
    texts = tuple(text for element in elements for text in name_sources(element))
    if texts:
        _SOURCES[key] = _SOURCES.get(key, ()) + texts
    if elements:
        _ELEMENTS[key] = _ELEMENTS.get(key, ()) + elements
    extra = tuple(url for url in urls if url)
    if extra:
        _URLS[key] = _URLS.get(key, ()) + extra


def ax_locator(element: ElementFact, **extra: object) -> Locator:
    raw = extra.pop("sources", ())
    group = tuple(raw) if isinstance(raw, (list, tuple)) else ()
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
    locator = Locator.model_validate(payload)
    note_sources(locator, element, *group)
    return locator


def stable_signature(*parts: str) -> str:
    folded = "|".join(_DIGIT.sub("#", match_key(part)) for part in parts)
    return hashlib.sha1(folded.encode()).hexdigest()[:12]


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


# These element reasons outrank a hard block. Disabled and missing do not.
_BEFORE_HARD = frozenset({"not visible", "aria-disabled", "inert", "covered", "requires sign-in"})


def login_gated(
    element: ElementFact,
    ctx: MapContext,
    affordance_id: str,
    *,
    action: str | None = None,
) -> bool:
    if affordance_id == "go_sign_in" or ctx.signed_in:
        return False
    if any(ctx.lexicon.login_label(text) for text in name_sources(element)):
        return True
    if any(text and ctx.lexicon.login_hint(text) for text in (element.title, element.described_by)):
        return True
    seen: list[str] = []
    for target in (element.href, element.form_action, action):
        if not target or target in seen:
            continue
        seen.append(target)
        account = ctx.lexicon.account_action(label=element.name, url=target)
        if ctx.lexicon.login_target(target, account_action=account):
            return True
    return False


def apply_hard_block(
    enabled: bool,
    reason: str | None,
    verb: str | None,
    lexicon: Lexicon,
) -> tuple[bool, str | None]:
    blocked = lexicon.hard_block(verb)
    if not blocked:
        return enabled, reason
    if reason in _BEFORE_HARD:
        return False, reason
    return False, blocked


def normalize(text: str) -> str:
    return normalize_label(text)


def _phrases(text: str) -> tuple[str, ...]:
    found = [text]
    for piece in re.split(r"[\s/#]+", text):
        tail = piece.rsplit(":", 1)[-1]
        stem = tail.removesuffix("Action")
        spaced = _CAMEL.sub(r"\1 \2", stem).replace("_", " ").replace("-", " ")
        if spaced and spaced not in found:
            found.append(spaced)
    return tuple(found)


def _hard_verb(lexicon: Lexicon, *texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        for phrase in _phrases(text):
            verb = lexicon.verb(phrase)
            if lexicon.hard_block(verb):
                return verb
    return None


def _needs_login(
    ctx: MapContext,
    affordance_id: str,
    texts: list[str],
    elements: tuple[ElementFact, ...],
    urls: tuple[str, ...],
) -> bool:
    if affordance_id == "go_sign_in" or ctx.signed_in:
        return False
    lexicon = ctx.lexicon
    if any(text and (lexicon.login_label(text) or lexicon.login_hint(text)) for text in texts):
        return True
    if any(login_gated(element, ctx, affordance_id) for element in elements):
        return True
    return any(
        lexicon.login_target(url, account_action=lexicon.account_action(url=url)) for url in urls
    )


def seal_hard_blocks(result: MapResult, ctx: MapContext) -> MapResult:
    updated: list[Affordance] = []
    for action in result.affordances:
        extra = action.x
        if extra is None:
            updated.append(action)
            continue
        texts = [extra.label or "", action.id]
        elements: tuple[ElementFact, ...] = ()
        urls: tuple[str, ...] = ()
        locator = extra.locator
        if locator is not None:
            texts.append(locator.name or "")
            if locator.tool:
                texts.append(locator.tool)
            texts.extend(locator.options or ())
            key = id(locator)
            texts.extend(_SOURCES.get(key, ()))
            elements = _ELEMENTS.get(key, ())
            urls = _URLS.get(key, ())
        for prop in action.input.properties.values():
            texts.extend(str(item) for item in prop.enum or ())
        verb = _hard_verb(ctx.lexicon, *texts)
        reason = extra.reason
        if isinstance(reason, str) and reason.startswith("hard-blocked in v1: "):
            current = reason.removeprefix("hard-blocked in v1: ")
            if ctx.lexicon.hard_block(current):
                verb = current
        if verb is None and any(element.input_type == "file" for element in elements):
            verb = "upload"
        login = _needs_login(ctx, action.id, texts, elements, urls)
        mixed = verb is None and any(text and suspect_label(text) for text in texts)
        if verb is None and not login and not mixed:
            updated.append(action)
            continue
        tag = extra.tag
        if login and reason not in _BEFORE_HARD:
            reason = "requires sign-in"
        elif mixed and reason not in _BEFORE_HARD:
            reason = "hard-blocked in v1: mixed-script label"
            tag = "mutating"
        elif verb is not None and reason not in _BEFORE_HARD:
            blocked = ctx.lexicon.hard_block(verb)
            if blocked:
                reason = blocked
        if verb is not None:
            tag = ctx.lexicon.tag(verb)
        updated.append(
            action.model_copy(
                update={
                    "enabled": False,
                    "x": extra.model_copy(update={"reason": reason, "tag": tag}),
                }
            )
        )
    result.affordances = updated
    _SOURCES.clear()
    _ELEMENTS.clear()
    _URLS.clear()
    return result
