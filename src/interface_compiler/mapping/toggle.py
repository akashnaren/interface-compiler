"""Checkbox and switch."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import field_name
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    stable_signature,
)


def map_checkbox(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    field = field_name(element)
    enabled, reason = element_enabled(element)
    checked = bool(element.checked) or element.aria_checked == "true"
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=input_schema({field: {"type": "boolean"}}, [field]),
                label=element.name or field,
                locator=ax_locator(element),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("checkbox", field, element.landmark),
            )
        ],
        state={field: checked},
        state_from={field: "control"},
    )
