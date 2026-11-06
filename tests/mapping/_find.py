"""Small assertions shared by the mapping tests."""

from __future__ import annotations

from interface_compiler.contract.models import Affordance
from interface_compiler.mapping import MapResult


def one(result: MapResult, affordance_id: str) -> Affordance:
    found = [item for item in result.affordances if item.id == affordance_id]
    assert len(found) == 1, [item.id for item in result.affordances]
    return found[0]


def props(item: Affordance) -> dict[str, object]:
    return {
        name: schema.model_dump(exclude_none=True) for name, schema in item.input.properties.items()
    }
