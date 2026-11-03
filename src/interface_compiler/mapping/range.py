"""Slider and spinbutton."""

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


def map_range(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    field = field_name(element)
    prop = property_for(element) or {"type": "number"}
    enabled, reason = element_enabled(element)
    current = element.aria_valuenow if element.aria_valuenow not in {None, ""} else element.value
    number = _number(current)
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
                signature=stable_signature("range", field, element.landmark),
            )
        ],
        state={field: number},
        state_from={field: "aria" if element.aria_valuenow else "control"},
    )


def _number(value: str | None) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number
