"""Action menus and option menus (R3)."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.button import map_button
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.link import map_link
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    affordance,
    ax_locator,
    input_schema,
    merge_results,
    stable_signature,
)


def map_menu(
    button: ElementFact,
    items: list[ElementFact],
    ctx: MapContext,
    *,
    disambiguate: bool,
) -> MapResult:
    if any(item.role in {"menuitemradio", "menuitemcheckbox"} for item in items):
        return _options(button, items, ctx)
    return _actions(button, items, ctx, disambiguate=disambiguate)


def _actions(
    button: ElementFact,
    items: list[ElementFact],
    ctx: MapContext,
    *,
    disambiguate: bool,
) -> MapResult:
    name = slug(button.name) or "menu"
    affordance_id = f"open_{name}_menu" if disambiguate else "open_menu"
    enabled, reason = element_enabled(button)
    closed = _closed(button, items)
    parts = [
        MapResult(
            affordances=[
                affordance(
                    affordance_id,
                    enabled=enabled,
                    label=button.name,
                    locator=ax_locator(button),
                    grain="single",
                    tag="safe",
                    reason=reason,
                    signature=stable_signature("menu", affordance_id, button.landmark),
                )
            ],
            state={f"{name}_menu_open": not closed},
            state_from={f"{name}_menu_open": "aria"},
        )
    ]
    if items and closed:
        for item in items:
            mapped = (
                map_link(item, ctx)
                if item.tag == "a" or item.role == "link"
                else map_button(item, ctx)
            )
            for action in mapped.affordances:
                if action.x is not None:
                    action.enabled = False
                    action.x.reason = "menu closed"
            parts.append(mapped)
    elif items:
        for item in items:
            mapped = (
                map_link(item, ctx)
                if item.tag == "a" or item.role == "link"
                else map_button(item, ctx)
            )
            parts.append(mapped)
    return merge_results(parts)


def _options(button: ElementFact, items: list[ElementFact], ctx: MapContext) -> MapResult:
    del ctx
    field = slug(button.name) or "option"
    closed = _closed(button, items)
    visible = [
        item.name
        for item in items
        if item.visible and not item.disabled and not item.aria_disabled and not item.hidden
    ]
    if closed or not visible:
        prop: dict[str, object] = {"type": "string"}
    else:
        prop = {"type": "string", "enum": visible}
    enabled, reason = element_enabled(button)
    selected = next((item.name for item in items if item.aria_checked == "true"), "")
    return MapResult(
        affordances=[
            affordance(
                f"set_{field}",
                enabled=enabled,
                schema=input_schema({field: prop}, [field]),
                label=button.name,
                locator=ax_locator(button, kind="group", options={name: name for name in visible}),
                grain="field",
                tag="safe",
                reason=reason,
                signature=stable_signature("menu-options", field, button.landmark),
            )
        ],
        state={f"selected_{field}": selected},
        state_from={f"selected_{field}": "aria"},
    )


def _closed(button: ElementFact, items: list[ElementFact]) -> bool:
    if button.aria_expanded == "false":
        return True
    return bool(items) and all(item.hidden or not item.visible for item in items)
