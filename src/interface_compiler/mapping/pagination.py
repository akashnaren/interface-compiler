"""Next, previous, and a page-number enum."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    stable_signature,
)


def map_pagination(links: list[ElementFact], ctx: MapContext) -> MapResult:
    result = MapResult()
    numbers: list[int] = []
    current: int | None = None
    for element in links:
        verb = ctx.lexicon.verb(element.name)
        if verb == "next_page":
            result.affordances.append(_step("next_page", element))
            continue
        if verb == "prev_page":
            result.affordances.append(_step("prev_page", element))
            continue
        if element.name.strip().isdigit():
            number = int(element.name.strip())
            if element.visible:
                numbers.append(number)
            if element.aria_current:
                current = number
    if numbers:
        result.affordances.append(
            affordance(
                "go_page",
                enabled=True,
                schema=input_schema(
                    {"page": {"type": "integer", "enum": numbers}},
                    ["page"],
                ),
                label="page",
                locator=ax_locator(
                    links[0], kind="group", options={str(number): str(number) for number in numbers}
                ),
                grain="field",
                tag="safe",
                signature=stable_signature("pagination", "go_page", links[0].landmark),
            )
        )
    if current is not None:
        result.state["page"] = current
        result.state_from["page"] = "aria"
    return result


def _step(affordance_id: str, element: ElementFact):
    enabled, reason = element_enabled(element)
    return affordance(
        affordance_id,
        enabled=enabled,
        label=element.name,
        locator=ax_locator(element),
        grain="single",
        tag="safe",
        reason=reason,
        signature=stable_signature("pagination", affordance_id, element.landmark),
    )
