"""Element to affordance mapping. One function per kind."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import assert_never

from interface_compiler.browser.facts import ElementFact, FormFact, ModalFact
from interface_compiler.extract.repeats import RepeatGroup
from interface_compiler.mapping.button import map_button
from interface_compiler.mapping.choice import map_choice_group
from interface_compiler.mapping.combobox import map_combobox
from interface_compiler.mapping.declared import map_schema_org_action, prefer_declared
from interface_compiler.mapping.dialog import apply_dialog
from interface_compiler.mapping.disclosure import map_disclosure
from interface_compiler.mapping.document import map_facts
from interface_compiler.mapping.form import map_form
from interface_compiler.mapping.link import map_link, map_link_groups
from interface_compiler.mapping.menu import map_menu
from interface_compiler.mapping.pagination import map_pagination
from interface_compiler.mapping.range import map_range
from interface_compiler.mapping.select import map_select
from interface_compiler.mapping.tabs import map_tabs
from interface_compiler.mapping.text import map_text_field
from interface_compiler.mapping.toggle import map_checkbox
from interface_compiler.mapping.types import MapContext, MapResult
from interface_compiler.mapping.webmcp import map_webmcp_tool

__all__ = [
    "DISPATCH",
    "Kind",
    "MapContext",
    "MapResult",
    "apply_dialog",
    "map_button",
    "map_checkbox",
    "map_choice_group",
    "map_combobox",
    "map_disclosure",
    "map_facts",
    "map_form",
    "map_kind",
    "map_link",
    "map_link_group",
    "map_link_groups",
    "map_menu",
    "map_pagination",
    "map_range",
    "map_schema_org_action",
    "map_select",
    "map_tabs",
    "map_text_field",
    "map_webmcp_tool",
    "prefer_declared",
]


class Kind(Enum):
    LINK = "link"
    LINK_GROUP = "link_group"
    BUTTON = "button"
    CHOICE = "choice"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXT = "text"
    FORM = "form"
    TABS = "tabs"
    DISCLOSURE = "disclosure"
    MENU = "menu"
    COMBOBOX = "combobox"
    RANGE = "range"
    DIALOG = "dialog"
    PAGINATION = "pagination"
    SCHEMA = "schema"
    WEBMCP = "webmcp"


def map_link_group(group: RepeatGroup, ctx: MapContext) -> MapResult:
    """One repeat group."""
    return map_link_groups([group], ctx)


def map_kind(kind: Kind, ctx: MapContext, payload: Mapping[str, object]) -> MapResult:
    """Dispatch one kind. Unknown kinds fail at type-check time."""
    match kind:
        case Kind.LINK:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_link(element, ctx)
        case Kind.LINK_GROUP:
            return map_link_group(payload["group"], ctx)
        case Kind.BUTTON:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_button(element, ctx)
        case Kind.CHOICE:
            options = payload["options"]
            if not isinstance(options, list):
                raise TypeError("options")
            return map_choice_group(options, ctx)
        case Kind.SELECT:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_select(element, ctx)
        case Kind.CHECKBOX:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_checkbox(element, ctx)
        case Kind.TEXT:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_text_field(element, ctx)
        case Kind.FORM:
            form = payload["form"]
            fields = payload["fields"]
            if not isinstance(form, FormFact) or not isinstance(fields, list):
                raise TypeError("form")
            return map_form(form, fields, ctx)
        case Kind.TABS:
            tabs = payload["tabs"]
            tablist = payload.get("tablist")
            if not isinstance(tabs, list):
                raise TypeError("tabs")
            return map_tabs(
                tablist if isinstance(tablist, ElementFact) else None,
                tabs,
                ctx,
                disambiguate=bool(payload.get("disambiguate")),
            )
        case Kind.DISCLOSURE:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_disclosure(element, ctx)
        case Kind.MENU:
            button = payload["button"]
            items = payload["items"]
            if not isinstance(button, ElementFact) or not isinstance(items, list):
                raise TypeError("menu")
            return map_menu(button, items, ctx, disambiguate=bool(payload.get("disambiguate")))
        case Kind.COMBOBOX:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_combobox(element, ctx)
        case Kind.RANGE:
            element = payload["element"]
            if not isinstance(element, ElementFact):
                raise TypeError("element")
            return map_range(element, ctx)
        case Kind.DIALOG:
            result = payload["result"]
            dialog = payload["dialog"]
            if not isinstance(result, MapResult) or not isinstance(dialog, ModalFact):
                raise TypeError("dialog")
            return apply_dialog(result, dialog, ctx)
        case Kind.PAGINATION:
            links = payload["links"]
            if not isinstance(links, list):
                raise TypeError("links")
            return map_pagination(links, ctx)
        case Kind.SCHEMA:
            action = payload["action"]
            if not isinstance(action, dict):
                raise TypeError("action")
            return map_schema_org_action(action, ctx)
        case Kind.WEBMCP:
            tool = payload["tool"]
            if not isinstance(tool, dict):
                raise TypeError("tool")
            return map_webmcp_tool(tool, ctx)
        case _ as unknown:
            assert_never(unknown)


DISPATCH = {kind: map_kind for kind in Kind}
