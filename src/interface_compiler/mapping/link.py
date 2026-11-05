"""Single links and collapsed link groups (R1, R4)."""

from __future__ import annotations

import base64
from urllib.parse import parse_qsl, urlsplit

from interface_compiler.browser.facts import ElementFact
from interface_compiler.contract.models import Locator
from interface_compiler.extract.naming import plural, slug
from interface_compiler.extract.repeats import RepeatGroup
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    apply_hard_block,
    ax_locator,
    input_schema,
    link_id,
    name_sources,
    note_sources,
    stable_signature,
)

_PAGE = 10


def map_link(element: ElementFact, ctx: MapContext) -> MapResult:
    affordance_id = link_id(element, ctx)
    enabled, reason = element_enabled(element)
    verb = ctx.lexicon.verb(element.name)
    enabled, reason = apply_hard_block(enabled, reason, verb, ctx.lexicon)
    tag = _link_tag(element, ctx)
    return MapResult(
        affordances=[
            affordance(
                affordance_id,
                enabled=enabled,
                label=element.name,
                locator=ax_locator(element),
                grain="single",
                tag=tag,
                reason=reason,
                signature=stable_signature("link", element.role, element.name, element.landmark),
            )
        ]
    )


def map_link_groups(groups: list[RepeatGroup], ctx: MapContext) -> MapResult:
    """One ``open_<entity>`` per entity type. Secondary links stay off unless asked."""
    by_entity: dict[str, list[tuple[ElementFact, list[ElementFact]]]] = {}
    by_action: dict[str, list[tuple[ElementFact, list[ElementFact]]]] = {}
    blocked: dict[str, ElementFact] = {}
    for group in groups:
        for item in group.items:
            links = [element for element in item.elements if _is_link(element)]
            if not links:
                continue
            primary = _primary(links)
            verb = _row_hard(ctx, [primary])
            if verb:
                blocked.setdefault(verb, primary)
                continue
            action = _account_verb(primary, ctx)
            if action:
                by_action.setdefault(action, []).append((primary, links))
                continue
            entity = _entity_name(primary.href or "")
            by_entity.setdefault(entity, []).append((primary, links))
    result = MapResult()
    for entity, rows in by_entity.items():
        result = _merge_entity(result, entity, rows, ctx, action=None)
    for verb, primary in blocked.items():
        result.affordances.append(
            affordance(
                verb,
                enabled=False,
                label=primary.name,
                locator=ax_locator(primary),
                grain="single",
                tag=ctx.lexicon.tag(verb),
                reason=ctx.lexicon.hard_block(verb),
                signature=stable_signature("hard-link", verb, primary.landmark),
            )
        )
    for action, rows in by_action.items():
        result = _merge_entity(result, action, rows, ctx, action=action)
    return result


def observe_page(records: list[dict[str, object]], cursor: str) -> list[dict[str, object]]:
    """The next fixed page of a list. The cursor is the one ``x.page`` issued."""
    _kind, offset = _decode(cursor)
    return records[offset : offset + _PAGE]


def _merge_entity(
    result: MapResult,
    entity: str,
    rows: list[tuple[ElementFact, list[ElementFact]]],
    ctx: MapContext,
    *,
    action: str | None,
) -> MapResult:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    secondaries: dict[str, ElementFact] = {}
    skipped: list[str] = []
    landmark = ""
    affordance_id = action or f"open_{entity}"
    for index, (primary, links) in enumerate(rows):
        enabled, reason = element_enabled(primary)
        landmark = landmark or primary.landmark
        for link in links:
            if link is primary:
                continue
            key = _secondary_slug(primary, link)
            if _row_hard(ctx, [link]):
                secondaries[key] = link
            else:
                secondaries.setdefault(key, link)
        if not enabled:
            if reason:
                skipped.append(reason)
            continue
        record_id = _record_id(primary, index, seen)
        seen.add(record_id)
        records.append({"id": record_id, "name": primary.name})
    if records:
        enabled, reason = True, None
    elif "requires sign-in" in skipped:
        enabled, reason = False, "requires sign-in"
    elif skipped:
        enabled, reason = False, skipped[0]
    else:
        enabled, reason = False, "not visible"
    key = plural(entity)
    prop = f"{entity}_id"
    tag = "mutating" if action else "safe"
    locator = Locator.model_validate(
        {
            "kind": "repeat",
            "role": "link",
            "name": entity,
            "landmark": landmark or None,
            "item_key": "href",
            "named_by": "rule",
        }
    )
    note_sources(locator, *(primary for primary, _links in rows))
    result.affordances.append(
        affordance(
            affordance_id,
            enabled=enabled,
            schema=input_schema({prop: {"type": "string"}}, [prop]),
            label=entity,
            locator=locator,
            grain="collapsed",
            tag=tag,
            reason=reason,
            signature=stable_signature("link-group", affordance_id, landmark),
        )
    )
    if records:
        window, cursor = _window(records, 0)
        result.entities[key] = window
        result.catalog[key] = records
        result.entities_from[key] = "repeat"
        result.page[key] = cursor
    for slug_key, link in secondaries.items():
        if action:
            continue
        token = f"{entity}.{slug_key}"
        wanted = (
            token in ctx.include_secondary or f"open_{entity}_{slug_key}" in ctx.include_secondary
        )
        if not wanted:
            continue
        secondary_id = f"open_{entity}_{slug_key}"
        sec_enabled, sec_reason = element_enabled(link)
        sec_verb = ctx.lexicon.verb(link.name)
        sec_enabled, sec_reason = apply_hard_block(sec_enabled, sec_reason, sec_verb, ctx.lexicon)
        result.affordances.append(
            affordance(
                secondary_id,
                enabled=sec_enabled,
                schema=input_schema({prop: {"type": "string"}}, [prop]),
                label=link.name,
                locator=ax_locator(link, kind="repeat", item_key="href"),
                grain="collapsed",
                tag=_link_tag(link, ctx),
                reason=sec_reason,
                signature=stable_signature("secondary", entity, slug_key, landmark),
            )
        )
    return result


def _window(
    records: list[dict[str, object]], offset: int
) -> tuple[list[dict[str, object]], dict[str, object]]:
    total = len(records)
    page = records[offset : offset + _PAGE]
    nxt = _encode(offset + _PAGE) if offset + _PAGE < total else None
    return page, {"offset": offset, "limit": _PAGE, "total": total, "next": nxt}


def _encode(offset: int) -> str:
    raw = f"page:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[str, int]:
    padded = cursor + "=" * (-len(cursor) % 4)
    text = base64.urlsafe_b64decode(padded).decode()
    _kind, offset = text.split(":")
    return _kind, int(offset)


def _is_link(element: ElementFact) -> bool:
    return element.tag == "a" or element.role == "link"


def _primary(links: list[ElementFact]) -> ElementFact:
    def rank(pair: tuple[int, ElementFact]) -> tuple[int, float, int]:
        index, element = pair
        in_heading = 0 if "heading >" in element.skeleton_path else 1
        area = -(element.box.width * element.box.height)
        return (in_heading, area, index)

    return min(enumerate(links), key=rank)[1]


def _entity_name(href: str) -> str:
    parts = [part for part in urlsplit(href).path.split("/") if part]
    if any(part in {"p", "product", "dp"} for part in parts):
        return "product"
    if any(part in {"s", "story", "stories"} for part in parts):
        return "story"
    return "item"


def _record_id(element: ElementFact, index: int, seen: set[str]) -> str:
    """Last path segment, plus the query id when that segment is shared."""
    parsed = urlsplit(element.href or "")
    parts = [part for part in parsed.path.split("/") if part]
    base = parts[-1] if parts else (slug(element.name) or "item")
    query_id = ""
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower() == "id" and value:
            query_id = value
            break
    if query_id:
        candidate = query_id
    elif parsed.query:
        candidate = f"{base}-{slug(parsed.query) or index}"
    else:
        candidate = base
    if candidate in seen:
        candidate = f"{candidate}-{index}"
    return candidate


def _row_hard(ctx: MapContext, links: list[ElementFact]) -> str | None:
    for link in links:
        for text in name_sources(link):
            verb = ctx.lexicon.verb(text)
            if ctx.lexicon.hard_block(verb):
                return verb
    return None


def _account_verb(element: ElementFact, ctx: MapContext) -> str | None:
    label = ctx.lexicon.verb(element.name)
    if label and ctx.lexicon.account_action(label=element.name):
        return label
    href = element.href or ""
    if not ctx.lexicon.account_action(url=href):
        return None
    parts = [part.casefold() for part in urlsplit(href).path.split("/") if part]
    return parts[-1] if parts else None


def _link_tag(element: ElementFact, ctx: MapContext) -> str:
    verb = ctx.lexicon.verb(element.name)
    if verb:
        return ctx.lexicon.tag(verb)
    if ctx.lexicon.account_action(url=element.href or ""):
        return "mutating"
    return "safe"


def _secondary_slug(primary: ElementFact, link: ElementFact) -> str:
    primary_parts = [part for part in urlsplit(primary.href or "").path.split("/") if part]
    link_parts = [part for part in urlsplit(link.href or "").path.split("/") if part]
    if len(link_parts) > len(primary_parts) and link_parts[: len(primary_parts)] == primary_parts:
        return slug(link_parts[-1]) or "link"
    return slug(link.name) or "link"
