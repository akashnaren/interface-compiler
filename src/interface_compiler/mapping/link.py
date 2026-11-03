"""Single links and collapsed link groups (R1, R4)."""

from __future__ import annotations

import base64
from urllib.parse import urlsplit

from interface_compiler.browser.facts import ElementFact
from interface_compiler.contract.models import Locator
from interface_compiler.extract.naming import plural, slug
from interface_compiler.extract.repeats import RepeatGroup
from interface_compiler.mapping.enabled import element_enabled, group_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    link_id,
    login_gated,
    stable_signature,
)

_PAGE = 10


def map_link(element: ElementFact, ctx: MapContext) -> MapResult:
    affordance_id = link_id(element, ctx)
    gated = login_gated(element, ctx, affordance_id)
    enabled, reason = element_enabled(element, login_gated=gated)
    tag = "safe"
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
    for group in groups:
        for item in group.items:
            links = [element for element in item.elements if _is_link(element)]
            if not links:
                continue
            primary = _primary(links)
            entity = _entity_name(primary.href or "")
            by_entity.setdefault(entity, []).append((primary, links))
    result = MapResult()
    for entity, rows in by_entity.items():
        result = _merge_entity(result, entity, rows, ctx)
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
) -> MapResult:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    secondaries: dict[str, ElementFact] = {}
    landmark = ""
    for primary, links in rows:
        record_id = _record_id(primary)
        if record_id in seen:
            continue
        seen.add(record_id)
        records.append({"id": record_id, "name": primary.name})
        landmark = landmark or primary.landmark
        for link in links:
            if link is primary:
                continue
            key = _secondary_slug(primary, link)
            secondaries.setdefault(key, link)
    key = plural(entity)
    window, cursor = _window(records, 0)
    enabled, reason = _group_enabled(rows)
    prop = f"{entity}_id"
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
    result.affordances.append(
        affordance(
            f"open_{entity}",
            enabled=enabled,
            schema=input_schema({prop: {"type": "string"}}, [prop]),
            label=entity,
            locator=locator,
            grain="collapsed",
            tag="safe",
            reason=reason,
            signature=stable_signature("link-group", entity, landmark),
        )
    )
    result.entities[key] = window
    result.catalog[key] = records
    result.entities_from[key] = "repeat"
    result.page[key] = cursor
    for slug_key, link in secondaries.items():
        token = f"{entity}.{slug_key}"
        wanted = (
            token in ctx.include_secondary or f"open_{entity}_{slug_key}" in ctx.include_secondary
        )
        if not wanted:
            continue
        result.affordances.append(
            affordance(
                f"open_{entity}_{slug_key}",
                enabled=enabled,
                schema=input_schema({prop: {"type": "string"}}, [prop]),
                label=link.name,
                locator=ax_locator(link, kind="repeat", item_key="href"),
                grain="collapsed",
                tag="safe",
                reason=reason,
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


def _group_enabled(
    rows: list[tuple[ElementFact, list[ElementFact]]],
) -> tuple[bool, str | None]:
    return group_enabled([item for item, _links in rows])


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


def _record_id(element: ElementFact) -> str:
    parts = [part for part in urlsplit(element.href or "").path.split("/") if part]
    if parts:
        return parts[-1]
    return slug(element.name) or "item"


def _secondary_slug(primary: ElementFact, link: ElementFact) -> str:
    primary_parts = [part for part in urlsplit(primary.href or "").path.split("/") if part]
    link_parts = [part for part in urlsplit(link.href or "").path.split("/") if part]
    if len(link_parts) > len(primary_parts) and link_parts[: len(primary_parts)] == primary_parts:
        return slug(link_parts[-1]) or "link"
    return slug(link.name) or "link"
