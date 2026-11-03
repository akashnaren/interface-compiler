"""WebMCP tools. Unknown schema keywords are dropped; objects flatten with ``_``."""

from __future__ import annotations

from typing import Any

from interface_compiler.contract.models import Locator
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    apply_hard_block,
    input_schema,
    stable_signature,
)

_KEEP = frozenset(
    {
        "type",
        "enum",
        "format",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "multipleOf",
        "items",
    }
)


def map_webmcp_tool(tool: dict[str, Any], ctx: MapContext) -> MapResult:
    name = slug(str(tool.get("name") or "tool")) or "tool"
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    read_only = annotations.get("readOnlyHint") is True
    properties, required = _properties(tool.get("inputSchema"))
    enabled, reason = apply_hard_block(
        True, None, name if ctx.lexicon.hard_block(name) else None, ctx.lexicon
    )
    tag = "safe" if read_only and reason is None else "mutating"
    locator = Locator.model_validate(
        {"kind": "webmcp", "tool": str(tool.get("name") or name), "named_by": "declared"}
    )
    return MapResult(
        affordances=[
            affordance(
                name,
                enabled=enabled,
                schema=input_schema(properties, required or None),
                label=str(tool.get("description") or name),
                locator=locator,
                grain="declared",
                tag=tag,
                reason=reason,
                signature=stable_signature("webmcp", name),
            )
        ]
    )


def _properties(schema: object) -> tuple[dict[str, dict[str, object]], list[str]]:
    if not isinstance(schema, dict):
        return {}, []
    raw = schema.get("properties")
    required_raw = schema.get("required")
    required = (
        [item for item in required_raw if isinstance(item, str)]
        if isinstance(required_raw, list)
        else []
    )
    properties: dict[str, dict[str, object]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict) and value.get("type") == "object":
                nested, _nested_required = _properties(value)
                for child, prop in nested.items():
                    properties[f"{slug(str(key))}_{child}"] = prop
                continue
            if isinstance(value, dict):
                properties[str(key)] = _keep(value)
    return properties, required


def _keep(value: dict[str, Any]) -> dict[str, object]:
    kept = {key: item for key, item in value.items() if key in _KEEP}
    if "type" not in kept:
        kept["type"] = "string"
    return kept
