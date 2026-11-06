"""Disclosure, accordion, and details/summary."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    stable_signature,
)


def map_disclosure(element: ElementFact, ctx: MapContext) -> MapResult:
    del ctx
    section = slug(element.name) or "section"
    enabled, reason = element_enabled(element)
    expanded = element.aria_expanded == "true"
    key = f"{section}_expanded"
    return MapResult(
        affordances=[
            affordance(
                f"toggle_{section}",
                enabled=enabled,
                label=element.name,
                locator=ax_locator(element),
                grain="single",
                tag="safe",
                reason=reason,
                signature=stable_signature("disclosure", section, element.landmark),
            )
        ],
        state={key: expanded},
        state_from={key: "aria"},
    )
