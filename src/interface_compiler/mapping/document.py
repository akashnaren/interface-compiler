"""Group a page of facts and map each group. No browser calls."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact, PageFacts
from interface_compiler.extract.repeats import find_repeat_groups
from interface_compiler.mapping.button import map_button
from interface_compiler.mapping.choice import map_choice_group
from interface_compiler.mapping.combobox import map_combobox
from interface_compiler.mapping.dialog import apply_dialog
from interface_compiler.mapping.disclosure import map_disclosure
from interface_compiler.mapping.form import map_form
from interface_compiler.mapping.link import map_link, map_link_groups
from interface_compiler.mapping.menu import map_menu
from interface_compiler.mapping.pagination import map_pagination
from interface_compiler.mapping.range import map_range
from interface_compiler.mapping.select import map_select
from interface_compiler.mapping.tabs import map_tabs
from interface_compiler.mapping.text import map_text_field
from interface_compiler.mapping.toggle import map_checkbox
from interface_compiler.mapping.types import (
    MapContext,
    MapResult,
    merge_results,
    note_sources,
    seal_hard_blocks,
)

_SKIP_ROLES = frozenset(
    {
        "heading",
        "navigation",
        "main",
        "banner",
        "contentinfo",
        "complementary",
        "form",
        "generic",
        "region",
        "menu",
        "option",
        "dialog",
        "tablist",
    }
)
_MENU_ITEMS = frozenset({"menuitem", "menuitemradio", "menuitemcheckbox"})


def map_facts(facts: PageFacts, ctx: MapContext | None = None) -> MapResult:
    context = ctx or MapContext(page_url=facts.url)
    elements = list(facts.elements)
    used: set[int] = set()
    parts: list[MapResult] = []

    parts.extend(_menus(elements, used, context))
    parts.extend(_tabs(elements, used, context))
    pagination = _pagination(elements, used, context)
    if pagination is not None:
        parts.append(pagination)
    parts.extend(_choices(elements, used, context))
    parts.extend(_forms(facts, elements, used, context))
    parts.extend(_repeats(elements, used, context))

    for element in elements:
        if id(element) in used or _skipped(element):
            continue
        mapped = _one(element, context)
        if mapped is not None:
            parts.append(mapped)
    result = merge_results(parts)
    top = _top_modal(facts.modals)
    if top is not None:
        result = apply_dialog(result, top, context)
    return seal_hard_blocks(result, context)


def _top_modal(modals: tuple) -> object:
    """The topmost modal, not whichever dialog the document listed first."""
    if not modals:
        return None
    for modal in modals:
        if modal.top:
            return modal
    return modals[-1]


def _menus(elements: list[ElementFact], used: set[int], ctx: MapContext) -> list[MapResult]:
    indexes = [index for index, element in enumerate(elements) if element.aria_haspopup == "menu"]
    if not indexes:
        return []
    disambiguate = len(indexes) > 1
    results: list[MapResult] = []
    for position, index in enumerate(indexes):
        button = elements[index]
        end = indexes[position + 1] if position + 1 < len(indexes) else len(elements)
        items = [element for element in elements[index + 1 : end] if element.role in _MENU_ITEMS]
        results.append(map_menu(button, items, ctx, disambiguate=disambiguate))
        used.add(id(button))
        used.update(id(item) for item in items)
    return results


def _tabs(elements: list[ElementFact], used: set[int], ctx: MapContext) -> list[MapResult]:
    groups: list[tuple[ElementFact | None, list[ElementFact]]] = []
    current: tuple[ElementFact | None, list[ElementFact]] | None = None
    for element in elements:
        if element.role == "tablist":
            current = (element, [])
            groups.append(current)
            used.add(id(element))
        elif element.role == "tab" and current is not None:
            current[1].append(element)
            used.add(id(element))
    many = len(groups) > 1
    return [map_tabs(tablist, tabs, ctx, disambiguate=many) for tablist, tabs in groups if tabs]


def _pagination(
    elements: list[ElementFact],
    used: set[int],
    ctx: MapContext,
) -> MapResult | None:
    links = [
        element
        for element in elements
        if element.landmark.startswith("navigation")
        and (element.tag == "a" or element.role == "link")
    ]
    if not any(ctx.lexicon.verb(element.name) in {"next_page", "prev_page"} for element in links):
        return None
    used.update(id(element) for element in links)
    return map_pagination(links, ctx)


def _choices(elements: list[ElementFact], used: set[int], ctx: MapContext) -> list[MapResult]:
    radios: dict[str, list[ElementFact]] = {}
    chips: dict[str, list[ElementFact]] = {}
    for element in elements:
        if id(element) in used:
            continue
        if element.role == "radio" and element.group_key:
            radios.setdefault(element.group_key, []).append(element)
        elif element.aria_pressed is not None and element.group_key:
            chips.setdefault(element.group_key, []).append(element)
    results: list[MapResult] = []
    for group in list(radios.values()) + list(chips.values()):
        results.append(map_choice_group(group, ctx))
        used.update(id(element) for element in group)
    return results


def _forms(
    facts: PageFacts,
    elements: list[ElementFact],
    used: set[int],
    ctx: MapContext,
) -> list[MapResult]:
    by_index: dict[int, list[ElementFact]] = {}
    for element in elements:
        if element.form_index is not None:
            by_index.setdefault(element.form_index, []).append(element)
    results: list[MapResult] = []
    for form in facts.forms:
        fields = [element for element in by_index.get(form.index, []) if id(element) not in used]
        if not fields:
            continue
        mapped = map_form(form, fields, ctx)
        for action in mapped.affordances:
            locator = action.x.locator if action.x else None
            if locator is not None and locator.kind == "form":
                note_sources(locator, *fields)
        results.append(mapped)
        used.update(id(element) for element in fields)
    return results


def _repeats(elements: list[ElementFact], used: set[int], ctx: MapContext) -> list[MapResult]:
    remaining = [element for element in elements if id(element) not in used]
    groups = [
        group
        for group in find_repeat_groups(remaining)
        if any(
            element.tag == "a" or element.role == "link"
            for item in group.items
            for element in item.elements
        )
    ]
    if not groups:
        return []
    for group in groups:
        for item in group.items:
            for element in item.elements:
                if element.tag == "a" or element.role == "link":
                    used.add(id(element))
    return [map_link_groups(groups, ctx)]


def _one(element: ElementFact, ctx: MapContext) -> MapResult | None:
    if element.tag == "a" or element.role == "link":
        return map_link(element, ctx)
    if element.tag == "summary" or (
        element.role == "button"
        and element.aria_expanded is not None
        and element.aria_haspopup != "menu"
    ):
        return map_disclosure(element, ctx)
    if element.role in {"checkbox", "switch"}:
        return map_checkbox(element, ctx)
    if element.tag == "select":
        return map_select(element, ctx)
    if element.role == "combobox":
        return map_combobox(element, ctx)
    if element.role in {"slider", "spinbutton"} or element.input_type in {"range", "number"}:
        return map_range(element, ctx)
    if element.input_type in {"submit", "image", "button", "reset"}:
        return map_button(element, ctx)
    if element.role in {"textbox", "searchbox"} or element.tag in {"textarea", "input"}:
        if element.form_index is None:
            return map_text_field(element, ctx)
        return None
    if element.role == "button" or element.tag == "button":
        return map_button(element, ctx)
    return None


def _skipped(element: ElementFact) -> bool:
    if element.tag in {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "nav",
        "main",
        "footer",
        "form",
        "dialog",
    }:
        return True
    return element.role in _SKIP_ROLES
