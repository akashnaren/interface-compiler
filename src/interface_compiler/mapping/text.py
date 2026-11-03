"""Text inputs and textareas outside a form."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import field_name
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.input_schema import property_for
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    stable_signature,
)


def map_text_field(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    field = field_name(element)
    prop = property_for(element) or {"type": "string"}
    enabled, reason = element_enabled(element, readonly=element.readonly)
    value: object = element.value or ""
    if element.input_type == "password":
        value = "<redacted>"
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=input_schema({field: prop}, [field]),
                label=element.name or field,
                locator=ax_locator(element),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("text", field, element.landmark),
            )
        ],
        state={field: value},
        state_from={field: "control"},
    )
