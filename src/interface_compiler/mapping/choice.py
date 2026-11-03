"""Radio, chip, and pressed-button groups become one ``set_<field>``."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.enabled import group_enabled, usable
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    stable_signature,
)


def map_choice_group(options: list[ElementFact], ctx: MapContext) -> MapResult:
    if not options:
        return MapResult()
    field = slug(options[0].group_key or options[0].label_text or options[0].name) or "choice"
    enabled_options = [option for option in options if usable(option)]
    labels = [option.name for option in enabled_options]
    selected = next((option.name for option in options if _selected(option)), "")
    sample = options[0]
    enabled, reason = group_enabled(options)
    if enabled and not labels:
        enabled, reason = False, "no options available"
    schema = input_schema(
        {field: {"type": "string", "enum": labels} if labels else {"type": "string"}}, [field]
    )
    key = f"selected_{field}"
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=schema,
                label=field,
                locator=ax_locator(
                    sample, kind="group", options={label: label for label in labels}
                ),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("choice", field, sample.landmark),
            )
        ],
        state={key: selected},
        state_from={key: "control"},
    )


def _selected(element: ElementFact) -> bool:
    if element.checked:
        return True
    return element.aria_pressed == "true" or element.aria_checked == "true"
