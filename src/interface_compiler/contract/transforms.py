"""Transforms over a compiled view document.

``strip_x`` is the paper-strict four-key document. ``ablate`` removes
``enabled`` and argument constraints for the constraint ablation. ``to_flat_tools``
builds a flat tool catalog from the same affordances.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from interface_compiler.contract.models import ViewDoc, dump_view_doc
from interface_compiler.contract.validate import _check_json_shape, _json_copy


def strip_x(doc: ViewDoc | Mapping[str, Any]) -> dict[str, Any]:
    """Return the document with top-level ``x`` and per-affordance ``x`` removed."""
    data = _as_document(doc)
    affordances = [
        {key: value for key, value in affordance.items() if key != "x"}
        for affordance in data["affordances"]
    ]
    return {
        "view": data["view"],
        "state": data["state"],
        "entities": data["entities"],
        "affordances": affordances,
    }


def ablate(doc: ViewDoc | Mapping[str, Any]) -> dict[str, Any]:
    """Remove ``enabled`` and argument constraints. Types stay.

    Stripped constraint keys are ``enum``, ``pattern``, ``required``, and keys
    that start with ``min``, ``max``, ``exclusiveMin``, or ``exclusiveMax``.
    ``format`` and ``multipleOf`` stay. ``x`` stays.
    """
    data = _as_document(doc)
    for affordance in data["affordances"]:
        affordance.pop("enabled", None)
        schema = affordance.get("input")
        if not isinstance(schema, dict):
            continue
        schema.pop("required", None)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            schema["properties"] = {
                name: _strip_constraints(prop) for name, prop in properties.items()
            }
    return data


def to_flat_tools(doc: ViewDoc | Mapping[str, Any]) -> list[dict[str, Any]]:
    """One tool per affordance. ``name`` is the id and ``parameters`` is ``input``."""
    data = _as_document(doc)
    return [
        {"name": affordance["id"], "parameters": _json_copy(affordance["input"])}
        for affordance in data["affordances"]
    ]


def extension_payload(doc: ViewDoc | Mapping[str, Any]) -> dict[str, Any]:
    """Return top-level ``x`` and per-affordance ``x``. Empty when neither is present."""
    raw = _as_document(doc)
    payload: dict[str, Any] = {}
    if "x" in raw:
        payload["x"] = raw["x"]
    affordance_x = [
        {"id": affordance.get("id"), "x": affordance["x"]}
        for affordance in raw["affordances"]
        if "x" in affordance
    ]
    if affordance_x:
        payload["affordances"] = affordance_x
    return payload


def _as_document(doc: ViewDoc | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(doc, ViewDoc):
        data: dict[str, Any] = dump_view_doc(doc)
    elif isinstance(doc, Mapping):
        data = dict(doc)
    else:
        raise TypeError("expected a compiled view document")
    _check_json_shape(data)
    return _json_copy(data)


def _strip_constraints(prop: object) -> object:
    if not isinstance(prop, dict):
        return _json_copy(prop)
    cleaned: dict[str, Any] = {}
    for key, value in prop.items():
        if _is_constraint(key):
            continue
        if key == "items":
            cleaned[key] = _strip_constraints(value)
            continue
        cleaned[key] = _json_copy(value)
    return cleaned


def _is_constraint(key: str) -> bool:
    return key in {"enum", "pattern"} or key.startswith(
        ("min", "max", "exclusiveMin", "exclusiveMax")
    )
