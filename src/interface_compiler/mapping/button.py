"""Buttons that are not part of a form, menu, tab, or choice group."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    apply_hard_block,
    ax_locator,
    button_id,
    stable_signature,
)


def map_button(element: ElementFact, ctx: MapContext) -> MapResult:
    affordance_id = button_id(element.name, ctx.lexicon)
    enabled, reason = element_enabled(element)
    enabled, reason = apply_hard_block(enabled, reason, ctx.lexicon.verb(element.name), ctx.lexicon)
    tag = ctx.lexicon.tag(ctx.lexicon.verb(element.name))
    state: dict[str, bool] = {}
    state_from: dict[str, str] = {}
    if element.aria_pressed is not None:
        key = slug(element.name) or affordance_id
        state[key] = element.aria_pressed == "true"
        state_from[key] = "aria"
    return MapResult(
        affordances=[
            affordance(
                affordance_id,
                enabled=enabled,
                label=element.name,
                locator=ax_locator(element),
                grain="single",
                tag=tag,
                reason=reason,
                signature=stable_signature("button", element.role, element.name, element.landmark),
            )
        ],
        state=state,
        state_from=state_from,
    )
