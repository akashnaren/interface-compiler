"""Open dialog post-pass."""

from __future__ import annotations

from interface_compiler.browser.facts import ModalFact
from interface_compiler.contract.models import Affordance
from interface_compiler.extract.naming import slug
from interface_compiler.mapping.types import MapContext, MapResult


def apply_dialog(result: MapResult, dialog: ModalFact, ctx: MapContext) -> MapResult:
    """Everything outside the open dialog is blocked. The close control stays."""
    del ctx
    updated: list[Affordance] = []
    for item in result.affordances:
        if _inside(item):
            updated.append(item)
            continue
        extra = item.x.model_copy(update={"reason": "blocked by dialog"}) if item.x else None
        updated.append(item.model_copy(update={"enabled": False, "x": extra}))
    result.affordances = updated
    name = slug(dialog.name or dialog.html_id or "dialog") or "dialog"
    result.state["dialog_open"] = name
    result.state_from["dialog_open"] = "aria"
    return result


def _inside(item: Affordance) -> bool:
    locator = item.x.locator if item.x else None
    if locator is None:
        return False
    extra = locator.model_extra or {}
    return extra.get("in_dialog") is True
