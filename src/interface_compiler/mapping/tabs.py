"""Tab lists."""

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


def map_tabs(
    tablist: ElementFact | None,
    tabs: list[ElementFact],
    ctx: MapContext,
    *,
    disambiguate: bool,
) -> MapResult:
    del ctx
    names = [tab.name for tab in tabs if usable(tab)]
    selected = next((tab.name for tab in tabs if tab.aria_selected == "true"), "")
    label = (tablist.name if tablist and tablist.name else "") or "tab"
    field = slug(label) or "tab"
    affordance_id = f"open_{field}_tab" if disambiguate else "open_tab"
    state_key = f"selected_{field}_tab" if disambiguate else "selected_tab"
    sample = tabs[0]
    prop_name = "tab"
    enabled, reason = group_enabled(tabs)
    return MapResult(
        affordances=[
            affordance(
                affordance_id,
                enabled=enabled and bool(names),
                schema=input_schema(
                    {prop_name: {"type": "string", "enum": names} if names else {"type": "string"}},
                    [prop_name],
                ),
                label=label,
                locator=ax_locator(
                    sample,
                    kind="group",
                    options={name: name for name in names},
                    sources=tuple(tabs),
                ),
                grain="field",
                tag="safe",
                reason=None if enabled and names else (reason or "not visible"),
                signature=stable_signature("tabs", affordance_id, sample.landmark),
            )
        ],
        state={state_key: selected},
        state_from={state_key: "aria"},
    )
