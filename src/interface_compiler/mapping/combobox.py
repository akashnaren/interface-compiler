"""Combobox and listbox. Closed popups are free text (R3)."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class OptionMatch:
    status: str
    code: str | None = None
    value: str | None = None


def map_combobox(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    field = field_name(element)
    values = enum_values(element)
    open_popup = element.aria_expanded == "true" and bool(values)
    always_open = element.role == "listbox" and element.aria_expanded is None and bool(values)
    if open_popup or always_open:
        prop: dict[str, object] = {"type": "string", "enum": values}
    else:
        prop = {"type": "string"}
        text = property_for(element)
        if text and element.tag != "select":
            for key in ("pattern", "minLength", "maxLength", "format"):
                if key in text:
                    prop[key] = text[key]
    enabled, reason = element_enabled(element, no_options=False)
    current = element.value or ""
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=input_schema({field: prop}, [field]),
                label=element.name or field,
                locator=ax_locator(
                    element, kind="group", options={value: value for value in values}
                ),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("combobox", field, element.landmark),
            )
        ],
        state={field: current},
        state_from={field: "control"},
    )


def match_option(value: str, options: list[str]) -> OptionMatch:
    """Case-insensitive exact label, then a unique prefix. Otherwise ``no_such_option``."""
    folded = value.casefold()
    exact = [option for option in options if option.casefold() == folded]
    if len(exact) == 1:
        return OptionMatch("ok", value=exact[0])
    if len(exact) > 1:
        return OptionMatch("invalid_args", code="no_such_option")
    prefix = [option for option in options if option.casefold().startswith(folded) and folded]
    if len(prefix) == 1:
        return OptionMatch("ok", value=prefix[0])
    return OptionMatch("invalid_args", code="no_such_option")
