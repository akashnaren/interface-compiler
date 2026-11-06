"""schema.org actions. A declared action replaces the inferred one with the same id."""

from __future__ import annotations

import json
import re

from interface_compiler.contract.models import Locator
from interface_compiler.extract.naming import alias, slug
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    apply_hard_block,
    input_schema,
    seal_hard_blocks,
    stable_signature,
)

_QUERY = re.compile(r"(required\s+)?name=([A-Za-z0-9_\-]+)")
_HARD_TYPES = {
    "BuyAction": "buy",
    "OrderAction": "order",
    "PayAction": "pay",
    "DeleteAction": "delete",
    "SendAction": "send",
    "CommunicateAction": "send",
    "TipAction": "tip",
    "DonateAction": "donate",
    "PreOrderAction": "preorder",
    "ReplyAction": "reply",
    "CommentAction": "comment",
    "AskAction": "ask",
}


def jsonld_nodes(html: str) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            nodes.append(parsed)
        elif isinstance(parsed, list):
            nodes.extend(item for item in parsed if isinstance(item, dict))
    return nodes


def map_schema_org_action(action: dict[str, object], ctx: MapContext) -> MapResult:
    raw_type = action.get("@type", "Action")
    parts = raw_type if isinstance(raw_type, list) and raw_type else [raw_type]
    type_name = str(parts[0])
    label = " ".join(str(part) for part in parts if part)
    verb = slug(type_name.removesuffix("Action")) or "action"
    properties: dict[str, dict[str, object]] = {}
    required: list[str] = []
    query = action.get("query-input")
    if isinstance(query, str):
        found = _QUERY.search(query)
        if found:
            name = alias(slug(found.group(2)))
            properties[name] = {"type": "string"}
            if found.group(1):
                required.append(name)
    target = action.get("target")
    template = target if isinstance(target, str) else ""
    if isinstance(target, dict):
        template = str(target.get("urlTemplate") or "")
    enabled, reason = True, None
    hard = None
    for part in parts:
        tail = _type_token(part)
        if tail in _HARD_TYPES:
            hard = _HARD_TYPES[tail]
            break
    if hard:
        enabled, reason = False, f"hard-blocked in v1: {hard}"
    elif verb in {"pay", "delete", "send"}:
        enabled, reason = apply_hard_block(enabled, reason, verb, ctx.lexicon)
    if verb == "search" and not hard:
        tag = "safe"
    elif hard:
        tag = "mutating"
    else:
        tag = ctx.lexicon.tag(verb, method="get" if verb == "search" else "post")
    locator = Locator.model_validate(
        {
            "kind": "jsonld",
            "url_template": template,
            "method": "GET" if verb == "search" else "POST",
            "named_by": "declared",
        }
    )
    return seal_hard_blocks(
        MapResult(
            affordances=[
                affordance(
                    verb,
                    enabled=enabled,
                    schema=input_schema(properties, required or None),
                    label=label,
                    locator=locator,
                    grain="declared",
                    tag=tag,
                    reason=reason,
                    signature=stable_signature("declared", verb, template),
                )
            ]
        ),
        ctx,
    )


def prefer_declared(inferred: MapResult, declared: list[MapResult]) -> MapResult:
    """Drop an inferred affordance when a declared action has the same id."""
    declared_ids = {item.id for part in declared for item in part.affordances}
    inferred.affordances = [item for item in inferred.affordances if item.id not in declared_ids]
    for part in declared:
        inferred.affordances.extend(part.affordances)
        inferred.state.update(part.state)
        inferred.state_from.update(part.state_from)
    return inferred


def product_from_jsonld(node: dict[str, object]) -> MapResult:
    if node.get("@type") != "Product":
        return MapResult()
    offers = node.get("offers")
    offer = offers if isinstance(offers, dict) else {}
    price = _price(offer.get("price") if isinstance(offer, dict) else None)
    record: dict[str, object] = {
        "id": str(node.get("sku") or node.get("@id") or node.get("productID") or ""),
        "name": str(node.get("name") or ""),
    }
    if price is not None:
        record["price"] = price
    currency = offer.get("priceCurrency") if isinstance(offer, dict) else None
    if isinstance(currency, str):
        record["price_currency"] = currency
    return MapResult(
        entities={"product": record}, entities_from={"product": "jsonld"}, view="product"
    )


def _type_token(value: object) -> str:
    """Strip space, drop a fragment and trailing slash, then take the last segment."""
    text = str(value).strip().split("#", 1)[0].rstrip("/").strip()
    cut = max(text.rfind("/"), text.rfind(":"))
    if cut >= 0:
        text = text[cut + 1 :]
    return text.strip()


def _price(value: object) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None
