"""Next, previous, and a page-number enum."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.mapping.enabled import element_enabled, group_enabled, usable
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
    page_links: list[ElementFact] = []
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
            page_links.append(element)
            if element.aria_current:
                current = int(element.name.strip())
    if page_links:
        numbers = [int(element.name.strip()) for element in page_links if usable(element)]
        enabled, reason = group_enabled(page_links)
        page_prop: dict[str, object] = (
            {"type": "integer", "enum": numbers} if numbers else {"type": "integer"}
        )
        result.affordances.append(
            affordance(
                "go_page",
                enabled=enabled and bool(numbers),
                schema=input_schema({"page": page_prop}, ["page"]),
                label="page",
                locator=ax_locator(
                    page_links[0],
                    kind="group",
                    options={str(number): str(number) for number in numbers},
                ),
                grain="field",
                tag="safe",
                reason=None if enabled and numbers else (reason or "not visible"),
                signature=stable_signature("pagination", "go_page", page_links[0].landmark),
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
