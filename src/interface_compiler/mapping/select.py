"""Native ``select`` keeps its enum, including when a menu would not."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import field_name
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.input_schema import enum_values, property_for
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    stable_signature,
)


def map_select(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    field = field_name(element)
    values = enum_values(element)
    prop = property_for(element) or {"type": "string"}
    enabled, reason = element_enabled(element, no_options=not values)
    selected = ""
    if element.value:
        for option in element.options:
            if option.value == element.value and not option.disabled and not _sold(option.label):
                selected = option.label.strip()
                break
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=input_schema({field: prop}, [field]),
                label=element.name or field,
                locator=ax_locator(
                    element,
                    kind="group",
                    options={value: value for value in values},
                ),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("select", field, element.landmark),
            )
        ],
        state={f"selected_{field}": selected},
        state_from={f"selected_{field}": "control"},
    )


def _sold(label: str) -> bool:
    text = label.casefold()
    return "sold out" in text or "unavailable" in text
